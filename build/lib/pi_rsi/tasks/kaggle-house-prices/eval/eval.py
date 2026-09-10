#!/usr/bin/env python3
"""Frozen evaluator for the Kaggle House Prices task.

Agent contract (run inside the worktree):
    <python> train.py --train <labeled.csv> --predict <features.csv> --out <pred.csv>
`pred.csv` has columns Id,SalePrice. Metric: RMSLE = RMSE between log1p(prediction) and log1p(truth), lower is better.

Modes (--seedset):
  quick      5-fold CV on the public train.csv (the worker's iteration signal; 5 trainings)
  validation hidden holdout (train on public train, predict eval/private/holdout.csv): the official node score
  kaggle     train on public + holdout, predict test.csv, submit with the kaggle CLI, wait for the public LB score

The harness runs its own copy of this file; edits to the in-repo copy do not change official scores.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PRIVATE = HERE.parent / "private" / "holdout.csv"
COMP = "house-prices-advanced-regression-techniques"
TRAIN_TIMEOUT_S = 900


def rmsle(pred: np.ndarray, truth: np.ndarray) -> float:
    pred = np.clip(np.asarray(pred, dtype=float), 1.0, None)
    return float(math.sqrt(np.mean((np.log1p(pred) - np.log1p(truth)) ** 2)))


def run_train(agent_dir: Path, python: str, train_csv: Path, predict_csv: Path, out_csv: Path, log) -> pd.DataFrame:
    cmd = [python, "train.py", "--train", str(train_csv), "--predict", str(predict_csv), "--out", str(out_csv)]
    log.write("$ " + " ".join(cmd) + "\n"); log.flush()
    p = subprocess.run(cmd, cwd=str(agent_dir), stdout=log, stderr=subprocess.STDOUT, timeout=TRAIN_TIMEOUT_S)
    if p.returncode != 0:
        raise RuntimeError(f"train.py exited with {p.returncode}")
    pred = pd.read_csv(out_csv)
    if not {"Id", "SalePrice"} <= set(pred.columns):
        raise RuntimeError("prediction file must have columns Id,SalePrice")
    if pred["SalePrice"].isna().any() or not np.isfinite(pred["SalePrice"]).all():
        raise RuntimeError("prediction contains NaN/inf")
    return pred


def aligned(pred: pd.DataFrame, truth: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    m = truth[["Id", "SalePrice"]].merge(pred[["Id", "SalePrice"]], on="Id", how="left", suffixes=("_true", "_pred"))
    if m["SalePrice_pred"].isna().any():
        raise RuntimeError(f"missing predictions for {int(m['SalePrice_pred'].isna().sum())} ids")
    return m["SalePrice_pred"].to_numpy(), m["SalePrice_true"].to_numpy()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent-dir", default=None)
    ap.add_argument("--seedset", default="quick", choices=["quick", "validation", "kaggle"])
    ap.add_argument("--out", default=None)
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--message", default="", help="kaggle submission message")
    a = ap.parse_args()
    agent_dir = Path(a.agent_dir).resolve() if a.agent_dir else HERE.parent
    out = Path(a.out) if a.out else agent_dir / f"metrics.{a.seedset}.json"
    work = Path(tempfile.mkdtemp(prefix="hp-eval-"))
    t0 = time.time()
    metrics: dict = {"seedset": a.seedset, "agent_dir": str(agent_dir), "metric": "rmsle", "higher_is_better": False}
    log = open(out.with_suffix(".log"), "w", encoding="utf-8")
    try:
        public = pd.read_csv(agent_dir / "data" / "train.csv")
        if a.seedset == "quick":
            rng = np.random.RandomState(20260910)
            folds = rng.permutation(len(public)) % 5
            scores = []
            for k in range(5):
                tr, va = public[folds != k], public[folds == k]
                tr.to_csv(work / f"tr{k}.csv", index=False)
                va.drop(columns=["SalePrice"]).to_csv(work / f"va{k}.csv", index=False)
                pred = run_train(agent_dir, a.python, work / f"tr{k}.csv", work / f"va{k}.csv", work / f"pred{k}.csv", log)
                p, t = aligned(pred, va)
                scores.append(rmsle(p, t))
            metrics.update(score=round(float(np.mean(scores)), 5), fold_scores=[round(s, 5) for s in scores],
                           score_std=round(float(np.std(scores)), 5), score_sem=round(float(np.std(scores) / math.sqrt(5)), 5), n=len(public))
        elif a.seedset == "validation":
            if not PRIVATE.exists():
                raise RuntimeError("hidden holdout missing; run prepare.py in the task pack")
            hold = pd.read_csv(PRIVATE)
            hold.drop(columns=["SalePrice"]).to_csv(work / "hold_x.csv", index=False)
            pred = run_train(agent_dir, a.python, agent_dir / "data" / "train.csv", work / "hold_x.csv", work / "pred.csv", log)
            p, t = aligned(pred, hold)
            per = (np.log1p(np.clip(p, 1, None)) - np.log1p(t)) ** 2
            ids = hold["Id"].to_numpy()
            metrics.update(score=round(rmsle(p, t), 5), n=len(hold), score_std=round(float(np.std(np.sqrt(per))), 5),
                           score_sem=round(float(np.std(per) / math.sqrt(len(per)) / (2 * max(rmsle(p, t), 1e-9))), 5),
                           per_item=[{"id": int(i), "value": float(v)} for i, v in zip(ids, per)], score_transform="sqrt_mean")
        else:  # kaggle
            hold = pd.read_csv(PRIVATE)
            full = pd.concat([public, hold], ignore_index=True)
            full.to_csv(work / "full.csv", index=False)
            pred = run_train(agent_dir, a.python, work / "full.csv", agent_dir / "data" / "test.csv", work / "submission.csv", log)
            sub = pred[["Id", "SalePrice"]]
            sub_path = agent_dir / "submission.csv"
            sub.to_csv(sub_path, index=False)
            msg = a.message or f"pi-rsi {agent_dir.name}"
            r = subprocess.run(["kaggle", "competitions", "submit", "-c", COMP, "-f", str(sub_path), "-m", msg],
                               capture_output=True, text=True, timeout=300)
            log.write(r.stdout + r.stderr + "\n")
            if r.returncode != 0:
                raise RuntimeError(f"kaggle submit failed: {r.stderr.strip()[:300]}")
            score = None
            for _ in range(40):  # poll up to ~10 min for the public score
                time.sleep(15)
                q = subprocess.run(["kaggle", "competitions", "submissions", "-c", COMP, "--csv"], capture_output=True, text=True, timeout=120)
                rows = list(csv_rows(q.stdout))
                mine = [x for x in rows if x.get("description") == msg]
                if mine and mine[0].get("status", "").lower() == "complete" and mine[0].get("publicScore"):
                    score = float(mine[0]["publicScore"])
                    break
            if score is None:
                raise RuntimeError("submission accepted but no public score returned in time")
            metrics.update(score=score, n=len(sub), submission=str(sub_path), message=msg)
        metrics["elapsed_s"] = round(time.time() - t0, 1)
    except Exception as e:
        metrics.update(score=None, error=f"{type(e).__name__}: {e}", elapsed_s=round(time.time() - t0, 1))
        out.write_text(json.dumps(metrics, indent=1))
        log.write(f"ERROR: {metrics['error']}\n"); log.close()
        print(f"EVAL ERROR: {metrics['error']} (log {out.with_suffix('.log')})", file=sys.stderr)
        shutil.rmtree(work, ignore_errors=True)
        return 1
    finally:
        pass
    log.close()
    shutil.rmtree(work, ignore_errors=True)
    out.write_text(json.dumps(metrics, indent=1))
    if not a.quiet:
        extra = f" folds={metrics.get('fold_scores')}" if a.seedset == "quick" else ""
        print(f"[{a.seedset}] rmsle={metrics['score']:.5f} (lower is better) n={metrics.get('n')}{extra} elapsed={metrics['elapsed_s']}s -> {out}")
    return 0


def csv_rows(text: str):
    import csv, io
    for row in csv.DictReader(io.StringIO(text)):
        yield row


if __name__ == "__main__":
    sys.exit(main())
