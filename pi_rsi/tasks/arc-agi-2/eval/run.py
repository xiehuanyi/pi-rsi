#!/usr/bin/env python3
"""Frozen job wrapper for ARC-AGI-2.

  python eval/run.py --budget <train seconds> --run-dir <dir> [--resume] [--level smoke|proxy|full] [--infer-budget S]

Loads the public training tasks and the level's evaluation subset (test outputs hidden), calls the solver
(`src/solver.py: solve(...)`), scores the returned predictions against the hidden outputs and writes:
  <run_dir>/metrics.jsonl   curve points from report(step, value) (used for stall/NaN detection)
  <run_dir>/metrics.json    score and diagnostics; score = pass2 + 0.001 * cell_acc (pass2 dominates)
  <run_dir>/predictions.json the predictions as returned (for audits)
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                       # worktree / task pack root
PRIVATE = (Path(__file__).resolve().parent.parent / "private" / "evaluation")
TASK_PACK_PRIVATE = Path("/media/xieh0a/data/huanyi/Research/AutoResearch/pi-rsi/pi_rsi/tasks/arc-agi-2/private/evaluation")
LEVEL_INFER_BUDGET = {"smoke": 300, "proxy": 1500, "full": 4500}
BUDGET_TO_LEVEL = {240: "smoke", 1800: "proxy", 7200: "full"}


def load_dir(d: Path) -> dict[str, dict]:
    return {f.stem: json.loads(f.read_text()) for f in sorted(d.glob("*.json"))}


def valid_grid(g) -> bool:
    return (isinstance(g, list) and 1 <= len(g) <= 30 and all(isinstance(r, list) and 1 <= len(r) <= 30 and len(r) == len(g[0])
            and all(isinstance(v, int) and 0 <= v <= 9 for v in r) for r in g))


def cell_acc(pred, gold) -> float:
    if not valid_grid(pred) or len(pred) != len(gold) or len(pred[0]) != len(gold[0]):
        return 0.0
    tot = len(gold) * len(gold[0])
    ok = sum(1 for r in range(len(gold)) for c in range(len(gold[0])) if pred[r][c] == gold[r][c])
    return ok / tot


def score_predictions(preds: dict, gold_tasks: dict) -> dict:
    per_item, n_inputs, valid, shape_ok = [], 0, 0, 0
    pass2_sum = pass1_sum = cell_sum = 0.0
    for tid, task in gold_tasks.items():
        tests = task["test"]
        task_pass2 = task_pass1 = True
        task_cell = 0.0
        for i, t in enumerate(tests):
            n_inputs += 1
            gold = t["output"]
            attempts = []
            try:
                attempts = list(preds.get(tid, [])[i])[:2]
            except (IndexError, TypeError):
                attempts = []
            attempts = [a for a in attempts if valid_grid(a)]
            valid += 1 if attempts else 0
            if any(len(a) == len(gold) and len(a[0]) == len(gold[0]) for a in attempts):
                shape_ok += 1
            correct = [a == gold for a in attempts]
            task_pass2 &= any(correct)
            task_pass1 &= bool(correct) and correct[0]
            task_cell += max([cell_acc(a, gold) for a in attempts] or [0.0])
        task_cell /= max(1, len(tests))
        pass2_sum += float(task_pass2)
        pass1_sum += float(task_pass1)
        cell_sum += task_cell
        per_item.append({"id": tid, "value": float(task_pass2) + 0.001 * task_cell, "pass2": bool(task_pass2), "cell_acc": round(task_cell, 4)})
    n = max(1, len(gold_tasks))
    pass2, pass1, cell = pass2_sum / n, pass1_sum / n, cell_sum / n
    return {"score": round(pass2 + 0.001 * cell, 6), "pass2": round(pass2, 4), "pass1": round(pass1, 4), "cell_acc": round(cell, 4),
            "shape_acc": round(shape_ok / max(1, n_inputs), 4), "valid_grid_rate": round(valid / max(1, n_inputs), 4),
            "n_tasks": len(gold_tasks), "n_test_inputs": n_inputs, "solved_tasks": [p["id"] for p in per_item if p["pass2"]],
            "per_item": per_item, "score_transform": "mean"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, required=True, help="training/search budget in seconds")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--level", default=None, help="smoke|proxy|full (default: inferred from --budget)")
    ap.add_argument("--infer-budget", type=float, default=None)
    a = ap.parse_args()
    level = a.level or BUDGET_TO_LEVEL.get(int(a.budget)) or "smoke"
    infer_budget = a.infer_budget or LEVEL_INFER_BUDGET.get(level, 600)
    run_dir = Path(a.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    subsets = json.loads((HERE / "subsets.json").read_text())
    ids = subsets[level]
    priv = PRIVATE if PRIVATE.exists() else TASK_PACK_PRIVATE
    gold_all = load_dir(priv)
    gold = {i: gold_all[i] for i in ids}
    eval_tasks = {i: {"train": gold[i]["train"], "test": [{"input": t["input"]} for t in gold[i]["test"]]} for i in ids}
    train_tasks = load_dir(ROOT / "data" / "training")
    curve_path = run_dir / "metrics.jsonl"
    if not a.resume and curve_path.exists():
        curve_path.unlink()
    t0 = time.time()

    def report(step, value, **extra):
        with open(curve_path, "a") as f:
            f.write(json.dumps({"step": int(step), "value": float(value), "t": round(time.time() - t0, 1), **extra}) + "\n")

    sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location("solver", ROOT / "src" / "solver.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    error = None
    preds = {}
    try:
        preds = mod.solve(train_tasks, eval_tasks, a.budget, str(run_dir), a.resume, report, infer_budget_s=infer_budget) or {}
    except Exception:
        error = traceback.format_exc()[-4000:]
        print(error, file=sys.stderr)
    train_elapsed = time.time() - t0
    (run_dir / "predictions.json").write_text(json.dumps(preds))
    m = score_predictions(preds, gold)
    m.update(level=level, train_budget_s=a.budget, infer_budget_s=infer_budget, elapsed_s=round(train_elapsed, 1), error=error)
    (run_dir / "metrics.json").write_text(json.dumps(m, indent=1))
    print(f"[{level}] score={m['score']:.5f} pass2={m['pass2']:.4f} pass1={m['pass1']:.4f} cell_acc={m['cell_acc']:.4f} "
          f"shape_acc={m['shape_acc']:.4f} valid={m['valid_grid_rate']:.3f} solved={m['solved_tasks']} elapsed={m['elapsed_s']}s")
    return 0 if error is None else 1


if __name__ == "__main__":
    sys.exit(main())
