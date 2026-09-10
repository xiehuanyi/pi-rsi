#!/usr/bin/env python3
"""Frozen evaluator for the Kaggle Spaceship Titanic task.

Agent contract (run inside the worktree):
    <python> train.py --train <labeled.csv> --predict <features.csv> --out <pred.csv>
`pred.csv` has columns PassengerId,Transported with True/False values. Metric: accuracy, higher is better.

Modes (--seedset):
  quick      5-fold CV on the public train.csv, grouped by passenger group (the worker's iteration signal)
  validation hidden holdout (train on public train, predict private/holdout.csv): the official node score
  kaggle     train on public + holdout, predict test.csv, submit with the kaggle CLI, wait for the public LB score
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
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
COMP = "spaceship-titanic"
TRAIN_TIMEOUT_S = 900


def to_bool(s: pd.Series) -> np.ndarray:
    if s.dtype == bool:
        return s.to_numpy()
    return s.astype(str).str.strip().str.lower().isin(["true", "1", "1.0", "yes"]).to_numpy()


def run_train(agent_dir: Path, python: str, train_csv: Path, predict_csv: Path, out_csv: Path, log) -> pd.DataFrame:
    cmd = [python, "train.py", "--train", str(train_csv), "--predict", str(predict_csv), "--out", str(out_csv)]
    log.write("$ " + " ".join(cmd) + "\n"); log.flush()
    p = subprocess.run(cmd, cwd=str(agent_dir), stdout=log, stderr=subprocess.STDOUT, timeout=TRAIN_TIMEOUT_S)
    if p.returncode != 0:
        raise RuntimeError(f"train.py exited with {p.returncode}")
    pred = pd.read_csv(out_csv)
    if not {"PassengerId", "Transported"} <= set(pred.columns):
        raise RuntimeError("prediction file must have columns PassengerId,Transported")
    if pred["Transported"].isna().any():
        raise RuntimeError("prediction contains missing values")
    return pred


def aligned(pred: pd.DataFrame, truth: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    m = truth[["PassengerId", "Transported"]].merge(pred[["PassengerId", "Transported"]], on="PassengerId", how="left", suffixes=("_true", "_pred"))
    if m["Transported_pred"].isna().any():
        raise RuntimeError(f"missing predictions for {int(m['Transported_pred'].isna().sum())} ids")
    return to_bool(m["Transported_pred"]), to_bool(m["Transported_true"]), m["PassengerId"].to_numpy()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent-dir", default=None)
    ap.add_argument("--seedset", default="quick", choices=["quick", "validation", "kaggle"])
    ap.add_argument("--out", default=None)
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--message", default="")
    a = ap.parse_args()
    agent_dir = Path(a.agent_dir).resolve() if a.agent_dir else HERE.parent
    out = Path(a.out) if a.out else agent_dir / f"metrics.{a.seedset}.json"
    work = Path(tempfile.mkdtemp(prefix="st-eval-"))
    t0 = time.time()
    metrics: dict = {"seedset": a.seedset, "agent_dir": str(agent_dir), "metric": "accuracy", "higher_is_better": True}
    log = open(out.with_suffix(".log"), "w", encoding="utf-8")
    try:
        public = pd.read_csv(agent_dir / "data" / "train.csv")
        if a.seedset == "quick":
            grp = public["PassengerId"].str.split("_").str[0]
            ug = grp.unique()
            rng = np.random.RandomState(20260910)
            rng.shuffle(ug)
            fold_of = {g: i % 5 for i, g in enumerate(ug)}
            folds = grp.map(fold_of).to_numpy()
            scores = []
            for k in range(5):
                tr, va = public[folds != k], public[folds == k]
                tr.to_csv(work / f"tr{k}.csv", index=False)
                va.drop(columns=["Transported"]).to_csv(work / f"va{k}.csv", index=False)
                pred = run_train(agent_dir, a.python, work / f"tr{k}.csv", work / f"va{k}.csv", work / f"pred{k}.csv", log)
                p, t, _ = aligned(pred, va)
                scores.append(float((p == t).mean()))
            metrics.update(score=round(float(np.mean(scores)), 5), fold_scores=[round(s, 5) for s in scores],
                           score_std=round(float(np.std(scores)), 5), score_sem=round(float(np.std(scores) / math.sqrt(5)), 5), n=len(public))
        elif a.seedset == "validation":
            if not PRIVATE.exists():
                raise RuntimeError("hidden holdout missing; run prepare.py in the task pack")
            hold = pd.read_csv(PRIVATE)
            hold.drop(columns=["Transported"]).to_csv(work / "hold_x.csv", index=False)
            pred = run_train(agent_dir, a.python, agent_dir / "data" / "train.csv", work / "hold_x.csv", work / "pred.csv", log)
            p, t, ids = aligned(pred, hold)
            correct = (p == t).astype(float)
            metrics.update(score=round(float(correct.mean()), 5), n=len(hold), score_std=round(float(correct.std()), 5),
                           score_sem=round(float(correct.std() / math.sqrt(len(correct))), 5),
                           per_item=[{"id": str(i), "value": float(c)} for i, c in zip(ids, correct)], score_transform="mean")
        else:
            hold = pd.read_csv(PRIVATE)
            full = pd.concat([public, hold], ignore_index=True)
            full.to_csv(work / "full.csv", index=False)
            pred = run_train(agent_dir, a.python, work / "full.csv", agent_dir / "data" / "test.csv", work / "submission.csv", log)
            sub = pd.DataFrame({"PassengerId": pred["PassengerId"], "Transported": to_bool(pred["Transported"])})
            sub_path = agent_dir / "submission.csv"
            sub.to_csv(sub_path, index=False)
            msg = a.message or f"pi-rsi {agent_dir.name}"
            r = subprocess.run(["kaggle", "competitions", "submit", "-c", COMP, "-f", str(sub_path), "-m", msg],
                               capture_output=True, text=True, timeout=300)
            log.write(r.stdout + r.stderr + "\n")
            if r.returncode != 0:
                raise RuntimeError(f"kaggle submit failed: {r.stderr.strip()[:300]}")
            score = None
            for _ in range(40):
                time.sleep(15)
                q = subprocess.run(["kaggle", "competitions", "submissions", "-c", COMP, "--csv"], capture_output=True, text=True, timeout=120)
                rows = list(csv.DictReader(io.StringIO(q.stdout)))
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
    log.close()
    shutil.rmtree(work, ignore_errors=True)
    out.write_text(json.dumps(metrics, indent=1))
    if not a.quiet:
        extra = f" folds={metrics.get('fold_scores')}" if a.seedset == "quick" else ""
        print(f"[{a.seedset}] accuracy={metrics['score']:.5f} (higher is better) n={metrics.get('n')}{extra} elapsed={metrics['elapsed_s']}s -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
