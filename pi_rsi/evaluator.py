"""Frozen evaluator invocation. The harness always runs the task pack's own copy of the evaluator against the
node's worktree, so a worker cannot change how it is scored."""
from __future__ import annotations

import json
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
             owner: str = "", incumbent_path: Path | None = None) -> dict[str, Any]:
    if cfg.task.job_enabled:
        return run_job_eval(cfg, worktree, seedset, out_dir, tag, owner, incumbent_path)
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


def score_of(cfg: ExperimentCfg, metrics: dict[str, Any]) -> float | None:
    v = metrics.get(cfg.task.score_key)
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def job_command(cfg: ExperimentCfg, level: str, run_dir: Path | str, resume: bool = False) -> list[str]:
    budget = cfg.task.job_budgets.get(level)
    if budget is None:
        raise EvalError(f"no job budget for level {level!r}; task.toml job_budgets has {sorted(cfg.task.job_budgets)}")
    cmd = cfg.task.job_command.format(python=_python(cfg), budget=budget, run_dir=str(run_dir),
                                      resume_flag="--resume" if resume else "", task_dir=str(cfg.task_dir))
    return shlex.split(cmd)


def run_job_eval(cfg: ExperimentCfg, worktree: Path, level: str, out_dir: Path, tag: str, owner: str,
                 incumbent_path: Path | None) -> dict[str, Any]:
    """Submit the evaluation as a queue job (GPU assignment, timeouts, early termination) and wait for it."""
    from . import jobs
    out_dir.mkdir(parents=True, exist_ok=True)
    run_dir = out_dir / f"run.{level}{('.' + tag) if tag else ''}"
    run_dir.mkdir(parents=True, exist_ok=True)
    name = f"metrics.{level}{('.' + tag) if tag else ''}.json"
    jobs.ensure_daemon()
    t0 = time.time()
    attempts = 2 if cfg.task.job_resumable else 1
    job = None
    for attempt in range(attempts):
        cmd = job_command(cfg, level, run_dir, resume=attempt > 0)
        es = dict(cfg.task.job_early_stop or {})
        if es:
            es.setdefault("higher_is_better", cfg.task.higher_is_better)
        job = jobs.submit(cmd, worktree, owner=owner, gpus=cfg.task.job_gpus, timeout_s=cfg.task.job_timeout_s,
                          stall_s=cfg.task.job_stall_s, metrics_path=str(run_dir / "metrics.jsonl"),
                          result_path=str(run_dir / "metrics.json"),
                          incumbent_path=str(incumbent_path) if (incumbent_path and es and Path(incumbent_path).exists()) else "",
                          early_stop=es if incumbent_path else {})
        (out_dir / (name.replace(".json", ".job"))).write_text(job.id)
        job = jobs.wait(job.id)
        if job.status == "done":
            break
        if job.status == "killed" and job.reason.startswith("early stop"):
            break
    assert job is not None
    metrics = read_json(run_dir / "metrics.json")
    if job.status == "killed" and job.reason.startswith("early stop"):
        raise EvalError(f"early-stopped: {job.reason}")
    if job.status != "done" or metrics is None:
        raise EvalError(f"job {job.id} {job.status}: {job.reason or 'no metrics.json'} (log {jobs.jobs_dir() / 'logs' / (job.id + '.log')})")
    metrics["_eval"] = {"seedset": level, "elapsed_s": round(time.time() - t0, 1), "job": job.id, "gpus": job.assigned_gpus,
                        "duration_s": job.duration_s, "run_dir": str(run_dir), "log": str(jobs.jobs_dir() / "logs" / (job.id + ".log"))}
    atomic_write_json(out_dir / name, metrics)
    return metrics
