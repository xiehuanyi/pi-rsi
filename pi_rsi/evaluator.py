"""Frozen evaluator invocation. The harness always runs the task pack's own copy of the evaluator against the
node's worktree, so a worker cannot change how it is scored."""
from __future__ import annotations

import json
import math
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

from .config import ExperimentCfg
from .util import atomic_write_json, read_json


class EvalError(RuntimeError):
    pass


def _python(cfg: ExperimentCfg) -> str:
    p = Path(cfg.task.python)
    if not p.is_absolute():
        cand = cfg.task_dir / p
        if cand.exists():
            return str(cand)
    return str(p)


def eval_command(cfg: ExperimentCfg, worktree: Path, seedset: str, out: Path) -> list[str]:
    cmd = cfg.task.eval_command.format(python=_python(cfg), task_dir=str(cfg.task_dir), worktree=str(worktree),
                                       seedset=seedset, out=str(out))
    return shlex.split(cmd)


def queued_eval(cfg: ExperimentCfg) -> bool:
    """Official evaluations run through the task queue, so a node can wait for one without holding a thread."""
    return bool(cfg.task.job_enabled or cfg.research.enabled)


def run_eval(cfg: ExperimentCfg, worktree: Path, seedset: str, out_dir: Path, tag: str = "",
             owner: str = "", incumbent_path: Path | None = None, resume: bool = False) -> dict[str, Any]:
    """`resume=True` continues an evaluation a previous controller started (same job, same attempt);
    otherwise a terminal failure of the same evaluation is retried from its first attempt."""
    if cfg.task.job_enabled:
        return run_job_eval(cfg, worktree, seedset, out_dir, tag, owner, incumbent_path, resume)
    if cfg.research.enabled:
        return run_monitored_eval(cfg, worktree, seedset, out_dir, tag, owner, resume)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"metrics.{seedset}{('.' + tag) if tag else ''}.json"
    out = out_dir / name
    log = out_dir / (name.replace(".json", ".log"))
    cmd = eval_command(cfg, worktree, seedset, out)
    t0 = time.time()
    with open(log, "w", encoding="utf-8") as lf:
        lf.write("$ " + " ".join(shlex.quote(c) for c in cmd) + "\n")
        lf.flush()
        try:
            p = subprocess.run(cmd, cwd=str(cfg.task_dir), stdout=lf, stderr=subprocess.STDOUT, text=True,
                               timeout=cfg.task.eval_timeout_s)
        except subprocess.TimeoutExpired:
            raise EvalError(f"evaluator timed out after {cfg.task.eval_timeout_s}s (see {log})")
    metrics = read_json(out)
    if p.returncode != 0 or metrics is None:
        raise EvalError(f"evaluator failed (exit {p.returncode}); see {log}")
    metrics["_eval"] = {"seedset": seedset, "elapsed_s": round(time.time() - t0, 1), "cmd": cmd, "log": str(log)}
    atomic_write_json(out, metrics)
    return metrics


def _early_stopped(job) -> bool:
    return job.status == "killed" and job.reason.startswith("early stop")


def _monitored_advance(monitor, commands, cwd, identity, *, aliases=None, resume=False, **options):
    """One step of an evaluation's attempt chain, without waiting: (job, pending).

    commands[k] is attempt k (k > 0 resumes). A queued/running/finished job of the same evaluation is
    reused; after a terminal failure the next attempt is submitted when one is left (resume=True), or
    attempt 0 again for a new evaluation request (resume=False, e.g. after an implementation retry).
    The attempt ordinal lives in the monitor record, so a restarted controller never collides with
    a live job or silently restarts training."""
    attempt, previous = monitor.last_attempt(identity, aliases)
    if previous is not None and previous.status in ("failed", "killed"):
        if not resume:
            attempt = 0
        elif _early_stopped(previous) or attempt + 1 >= len(commands):
            return previous, False  # that evaluation already ended for good
        else:
            attempt += 1
    job = monitor.submit(commands[attempt], cwd, identity=identity, attempt=attempt, aliases=aliases, **options)
    return job, job.status in ("queued", "running")


def _monitored_attempts(monitor, commands, cwd, identity, *, aliases=None, resume=False, **options):
    """Run one evaluation through its task monitor to its end (the blocking form of the chain above)."""
    job, pending = _monitored_advance(monitor, commands, cwd, identity, aliases=aliases, resume=resume, **options)
    while pending:
        monitor.wait(job.id)
        job, pending = _monitored_advance(monitor, commands, cwd, identity, aliases=aliases, resume=True, **options)
    monitor.refresh(job)  # the terminal state is on record even when no wait was needed
    return job


def _eval_spec(cfg, worktree, seedset, out_dir, tag="", owner="", incumbent_path=None):
    """Everything a queued official evaluation needs, derived from the configuration and the worktree alone,
    so that a waiting evaluation can be re-attached by a later poll or a restarted controller."""
    from .monitor import TaskMonitor, evaluation_identity
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"metrics.{seedset}{('.' + tag) if tag else ''}.json"
    monitor = TaskMonitor(out_dir / name.replace(".json", ".monitor.json"))
    if cfg.task.job_enabled:
        run_dir = out_dir / f"run.{seedset}{('.' + tag) if tag else ''}"
        run_dir.mkdir(parents=True, exist_ok=True)
        commands = [job_command(cfg, seedset, run_dir, resume=k > 0) for k in range(2 if cfg.task.job_resumable else 1)]
        # One identity per evaluation, independent of the attempt (the --resume flag is not identity).
        identity = evaluation_identity(cfg, worktree, commands[0])
        aliases = {TaskMonitor.fingerprint(evaluation_identity(cfg, worktree, c)): k
                   for k, c in enumerate(commands) if k}
        es = dict(cfg.task.job_early_stop or {})
        if es:
            es.setdefault("higher_is_better", cfg.task.higher_is_better)
        options = dict(owner=owner, gpus=cfg.task.job_gpus, timeout_s=cfg.task.job_timeout_s,
                       stall_s=cfg.task.job_stall_s, metrics_path=str(run_dir / "metrics.jsonl"),
                       result_path=str(run_dir / "metrics.json"),
                       incumbent_path=str(incumbent_path) if (incumbent_path and es and Path(incumbent_path).exists()) else "",
                       early_stop=es if incumbent_path else {}, priority=1)
        return {"kind": "job", "monitor": monitor, "commands": commands, "identity": identity, "aliases": aliases,
                "cwd": worktree, "options": options, "out": out_dir / name, "run_dir": run_dir}
    cmd = eval_command(cfg, worktree, seedset, out_dir / name)
    options = dict(owner=owner, gpus=0, timeout_s=cfg.task.eval_timeout_s, stall_s=0,
                   result_path=str(out_dir / name), priority=1)
    return {"kind": "monitored", "monitor": monitor, "commands": [cmd], "identity": evaluation_identity(cfg, worktree, cmd),
            "aliases": {}, "cwd": cfg.task_dir, "options": options, "out": out_dir / name, "run_dir": None}


def begin_eval(cfg, worktree, seedset, out_dir, tag="", owner="", incumbent_path=None, resume=False) -> bool:
    """Submit the official evaluation to the task queue, or re-attach to the one already submitted, and return
    without waiting. True while it is queued or running. False once its result can be collected: run_eval(...,
    resume=True) then returns immediately. A synchronous evaluator (no queue) is never pending."""
    if not queued_eval(cfg):
        return False
    spec = _eval_spec(cfg, worktree, seedset, out_dir, tag, owner, incumbent_path)
    try:
        job, pending = _monitored_advance(spec["monitor"], spec["commands"], spec["cwd"], spec["identity"],
                                          aliases=spec["aliases"], resume=resume, **spec["options"])
    except (RuntimeError, FileNotFoundError) as e:
        if isinstance(e, EvalError):
            raise
        raise EvalError(f"task monitor failed: {e}") from e
    spec["monitor"].refresh(job)
    if pending:
        from . import jobs
        jobs.ensure_daemon()  # a poll keeps the queue alive exactly as a blocking wait would
    return pending


def eval_pending(cfg, worktree, seedset, out_dir, tag="", owner="", incumbent_path=None) -> bool:
    """Poll a submitted evaluation: continue its attempt chain when an attempt failed and another is allowed,
    refresh the monitor record (state, progress) and report whether it is still queued or running."""
    return begin_eval(cfg, worktree, seedset, out_dir, tag, owner, incumbent_path, resume=True)


def run_monitored_eval(cfg, worktree, seedset, out_dir, tag, owner, resume=False):
    """Ordinary CPU evaluations use the same external queue/monitor as training jobs."""
    spec = _eval_spec(cfg, worktree, seedset, out_dir, tag, owner)
    monitor, out, cmd = spec["monitor"], spec["out"], spec["commands"][0]
    t0 = time.time()
    try:
        job = _monitored_attempts(monitor, spec["commands"], spec["cwd"], spec["identity"], resume=resume,
                                  **spec["options"])
        metrics = read_json(out)
        if job.status != "done" or not isinstance(metrics, dict) or score_of(cfg, metrics) is None:
            monitor.save(state="invalid" if job.status == "done" else job.status, wake_ready=False)
            raise EvalError(f"monitored task {job.id} {job.status}: {job.reason or 'no valid metric'}")
        from . import jobs
        metrics["_eval"] = {"seedset": seedset, "elapsed_s": round(time.time() - t0, 1),
            "cmd": cmd, "job": job.id, "monitor": str(monitor.path),
            "log": str(jobs.jobs_dir() / "logs" / (job.id + ".log"))}
        atomic_write_json(out, metrics)
        monitor.validated(out)
        return metrics
    except (RuntimeError, FileNotFoundError) as e:
        if isinstance(e, EvalError):
            raise
        raise EvalError(f"task monitor failed: {e}") from e


def score_of(cfg: ExperimentCfg, metrics: dict[str, Any]) -> float | None:
    v = metrics.get(cfg.task.score_key)
    try:
        score = float(v) if v is not None and not isinstance(v, bool) else None
        return score if score is not None and math.isfinite(score) else None
    except (TypeError, ValueError, OverflowError):
        return None


def job_command(cfg: ExperimentCfg, level: str, run_dir: Path | str, resume: bool = False) -> list[str]:
    budget = cfg.task.job_budgets.get(level)
    if budget is None:
        raise EvalError(f"no job budget for level {level!r}; task.toml job_budgets has {sorted(cfg.task.job_budgets)}")
    cmd = cfg.task.job_command.format(python=_python(cfg), budget=budget, run_dir=str(run_dir),
                                      resume_flag="--resume" if resume else "", task_dir=str(cfg.task_dir))
    return shlex.split(cmd)


def run_job_eval(cfg: ExperimentCfg, worktree: Path, level: str, out_dir: Path, tag: str, owner: str,
                 incumbent_path: Path | None, resume: bool = False) -> dict[str, Any]:
    """Submit the evaluation as a queue job (GPU assignment, timeouts, early termination) and wait for it."""
    from . import jobs
    from .monitor import TaskMonitor, evaluation_identity
    out_dir.mkdir(parents=True, exist_ok=True)
    run_dir = out_dir / f"run.{level}{('.' + tag) if tag else ''}"
    run_dir.mkdir(parents=True, exist_ok=True)
    name = f"metrics.{level}{('.' + tag) if tag else ''}.json"
    # An explicitly sealed, fixed-artifact confirmation may be restored only at
    # the final stage. It is not visible to the research controller during search.
    if tag == "final":
        sealed = cfg.dir / "private" / "sealed_confirmations" / out_dir.parent.name / name
        descriptor = read_json(sealed.with_suffix(".identity.json"), {}) or {}
        if sealed.exists():
            from .gitops import head
            from .memory import ResearchMemory
            import hashlib
            if (descriptor.get("commit") != head(worktree)
                    or descriptor.get("protocol") != ResearchMemory(cfg).protocol
                    or descriptor.get("sha256") != hashlib.sha256(sealed.read_bytes()).hexdigest()):
                raise EvalError("sealed confirmation identity does not match this artifact/protocol")
            metrics = read_json(sealed)
            if score_of(cfg, metrics) is None:
                raise EvalError("sealed confirmation contains no finite score")
            metrics["_eval"] = {**metrics.get("_eval", {}), "sealed_reuse": True}
            atomic_write_json(out_dir / name, metrics)
            return metrics
    monitor = TaskMonitor(out_dir / name.replace(".json", ".monitor.json"))
    jobs.ensure_daemon()
    t0 = time.time()
    job = None
    prev_file = out_dir / (name.replace(".json", ".job"))
    if prev_file.exists() and not monitor.path.exists():   # compatibility with older unmonitored job records
        try:
            prev = jobs.Job.load(prev_file.read_text().strip())
            if prev.status in ("queued", "running"):
                prev = jobs.wait(prev.id)
            if prev.status == "done" and (run_dir / "metrics.json").exists():
                job = prev
        except FileNotFoundError:
            pass
    if job is None:
        spec = _eval_spec(cfg, worktree, level, out_dir, tag, owner, incumbent_path)
        try:
            job = _monitored_attempts(monitor, spec["commands"], worktree, spec["identity"], aliases=spec["aliases"],
                                      resume=resume, **spec["options"])
        except RuntimeError as e:  # monitor refused (e.g. a different evaluation is still running)
            raise EvalError(f"task monitor failed: {e}") from e
        prev_file.write_text(job.id)
    metrics = read_json(run_dir / "metrics.json")
    if _early_stopped(job):
        raise EvalError(f"early-stopped: {job.reason}")
    if job.status != "done" or metrics is None:
        raise EvalError(f"job {job.id} {job.status}: {job.reason or 'no metrics.json'} (log {jobs.jobs_dir() / 'logs' / (job.id + '.log')})")
    if score_of(cfg, metrics) is None:
        raise EvalError(f"job {job.id} completed without a finite {cfg.task.score_key}")
    # Old completed .job records are adopted into the explicit monitor projection.
    monitor.save(job=job.id, state="done", wake_ready=False)
    metrics["_eval"] = {"seedset": level, "elapsed_s": round(time.time() - t0, 1), "job": job.id, "gpus": job.assigned_gpus,
                        "monitor": str(monitor.path),
                        "duration_s": job.duration_s, "run_dir": str(run_dir), "log": str(jobs.jobs_dir() / "logs" / (job.id + ".log"))}
    atomic_write_json(out_dir / name, metrics)
    monitor.validated(run_dir / "metrics.json")
    return metrics
