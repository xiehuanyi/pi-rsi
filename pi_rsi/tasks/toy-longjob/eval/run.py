#!/usr/bin/env python3
"""Frozen job wrapper for the toy long-job task: fixed data, curve logging, scoring, checkpoint-aware resume."""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def make_data(seed: int = 7, n: int = 6000, d: int = 20):
    rng = np.random.RandomState(seed)
    x = rng.randn(n, d)
    w = rng.randn(d)
    y = np.sin(x @ w / 3.0) * 3 + 0.5 * (x[:, 0] * x[:, 1]) + 0.3 * rng.randn(n)
    n_tr, n_va = int(n * 0.6), int(n * 0.2)
    return {"x_train": x[:n_tr], "y_train": y[:n_tr], "x_val": x[n_tr:n_tr + n_va], "y_val": y[n_tr:n_tr + n_va],
            "x_test": x[n_tr + n_va:], "y_test": y[n_tr + n_va:]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--resume", action="store_true")
    a = ap.parse_args()
    run_dir = Path(a.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    data = make_data()
    sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location("trainer", ROOT / "src" / "trainer.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    curve_path = run_dir / "metrics.jsonl"
    if not a.resume and curve_path.exists():
        curve_path.unlink()
    t0 = time.time()
    best = [math.inf]

    def report(step: int, val_pred):
        rmse = float(np.sqrt(np.mean((np.asarray(val_pred).reshape(-1) - data["y_val"]) ** 2)))
        best[0] = min(best[0], rmse)
        with open(curve_path, "a") as f:
            f.write(json.dumps({"step": int(step), "value": rmse, "t": round(time.time() - t0, 2)}) + "\n")

    pub = {k: v for k, v in data.items() if k != "y_test"}
    test_pred = mod.train(a.budget, str(run_dir), a.resume, pub, report)
    test_rmse = float(np.sqrt(np.mean((np.asarray(test_pred).reshape(-1) - data["y_test"]) ** 2)))
    n_steps = sum(1 for _ in open(curve_path)) if curve_path.exists() else 0
    (run_dir / "metrics.json").write_text(json.dumps({"score": round(test_rmse, 5), "best_val_rmse": round(best[0], 5),
                                                     "epochs": n_steps, "elapsed_s": round(time.time() - t0, 1), "budget_s": a.budget}, indent=1))
    print(f"test_rmse={test_rmse:.5f} best_val={best[0]:.5f} epochs={n_steps}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
