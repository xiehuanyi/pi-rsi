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


def run_eval(cfg: ExperimentCfg, worktree: Path, seedset: str, out_dir: Path, tag: str = "") -> dict[str, Any]:
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
