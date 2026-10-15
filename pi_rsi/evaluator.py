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


def _monitored_attempts(monitor, commands, cwd, identity, *, aliases=None, resume=False, **options):
    """Run one evaluation through its task monitor; commands[k] is attempt k (k > 0 resumes).

    The attempt ordinal lives in the monitor record, not in this loop: a restarted controller
    (resume=True) waits on the same queued/running job or continues with the next attempt instead
    of resubmitting attempt 0, which would collide with the live job or silently restart training."""
    attempt, previous = monitor.last_attempt(identity, aliases)
    if previous is not None and previous.status in ("failed", "killed"):
        if not resume:
            attempt = 0  # a new evaluation request (e.g. after an implementation retry)
        elif _early_stopped(previous) or attempt + 1 >= len(commands):
            return previous  # that evaluation already ended for good
        else:
            attempt += 1
    while True:
        job = monitor.submit(commands[attempt], cwd, identity=identity, attempt=attempt, aliases=aliases, **options)
        attempt = monitor.attempt(attempt)  # a reused live/finished job keeps its own attempt
        job = monitor.wait(job.id)
        if job.status == "done" or _early_stopped(job) or attempt + 1 >= len(commands):
            return job
        attempt += 1


def run_monitored_eval(cfg, worktree, seedset, out_dir, tag, owner, resume=False):
    """Ordinary CPU evaluations use the same external queue/monitor as training jobs."""
    from .monitor import TaskMonitor, evaluation_identity
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"metrics.{seedset}{('.' + tag) if tag else ''}.json"
    out = out_dir / name
    monitor = TaskMonitor(out_dir / name.replace(".json", ".monitor.json"))
    cmd = eval_command(cfg, worktree, seedset, out)
    t0 = time.time()
    try:
        job = _monitored_attempts(monitor, [cmd], cfg.task_dir, evaluation_identity(cfg, worktree, cmd),
                                  resume=resume, owner=owner, gpus=0, timeout_s=cfg.task.eval_timeout_s,
                                  stall_s=0, result_path=str(out))
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
        commands = [job_command(cfg, level, run_dir, resume=k > 0) for k in range(2 if cfg.task.job_resumable else 1)]
        # One identity per evaluation, independent of the attempt (the --resume flag is not identity).
        identity = evaluation_identity(cfg, worktree, commands[0])
        aliases = {TaskMonitor.fingerprint(evaluation_identity(cfg, worktree, c)): k
                   for k, c in enumerate(commands) if k}
        es = dict(cfg.task.job_early_stop or {})
        if es:
            es.setdefault("higher_is_better", cfg.task.higher_is_better)
        try:
            job = _monitored_attempts(
                monitor, commands, worktree, identity, aliases=aliases, resume=resume,
                owner=owner, gpus=cfg.task.job_gpus, timeout_s=cfg.task.job_timeout_s,
                stall_s=cfg.task.job_stall_s, metrics_path=str(run_dir / "metrics.jsonl"),
                result_path=str(run_dir / "metrics.json"),
                incumbent_path=str(incumbent_path) if (incumbent_path and es and Path(incumbent_path).exists()) else "",
                early_stop=es if incumbent_path else {})
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
