#!/usr/bin/env python3
"""Frozen evaluator for the Spaceship Titanic task pack (st-auto).

Agent contract (run inside the worktree):
    <python> train.py --train <labeled.csv> --predict <features.csv> --out <pred.csv>
`pred.csv` has columns PassengerId,Transported with True/False values.
Metric: accuracy, higher is better.

Modes (--seedset):
  quick       5-fold group-aware stratified CV on public train.csv (worker iteration signal)
  validation  hidden holdout: train on public train, predict private/holdout.csv (official node score)
  final       train on public + holdout, predict test.csv, submit with the kaggle CLI, wait for public LB

The harness always runs this file from the task pack, so edits in a worktree copy do not change official scores.
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
from sklearn.model_selection import StratifiedGroupKFold

HERE = Path(__file__).resolve().parent
TASK_DIR = HERE.parent
PRIVATE = TASK_DIR / "private" / "holdout.csv"
COMP = "spaceship-titanic"
TRAIN_TIMEOUT_S = 900
SEED = 20260910
N_FOLDS = 5


def to_bool(s: pd.Series) -> np.ndarray:
    if pd.api.types.is_bool_dtype(s):
        return s.fillna(False).to_numpy()
    if pd.api.types.is_numeric_dtype(s):
        num = pd.to_numeric(s, errors="coerce")
        if num.isna().any():
            raise RuntimeError("prediction contains missing numeric Transported values")
        return (num >= 0.5).to_numpy()
    sl = s.astype(str).str.strip().str.lower()
    mapped = sl.map(
        {"true": True, "false": False, "1": True, "0": False, "1.0": True, "0.0": False, "yes": True, "no": False}
    )
    if mapped.isna().any():
        num = pd.to_numeric(s, errors="coerce")
        mapped = mapped.fillna(num >= 0.5)
    if mapped.isna().any():
        raise RuntimeError("could not parse Transported predictions as booleans")
    return mapped.to_numpy(dtype=bool)


def labels_to_bool(s: pd.Series) -> np.ndarray:
    if pd.api.types.is_bool_dtype(s):
        return s.to_numpy()
    if pd.api.types.is_numeric_dtype(s):
        return (pd.to_numeric(s, errors="coerce") >= 0.5).to_numpy()
    return s.astype(str).str.strip().str.lower().isin(["true", "1", "1.0", "yes"]).to_numpy()


def run_train(agent_dir: Path, python: str, train_csv: Path, predict_csv: Path, out_csv: Path, log) -> pd.DataFrame:
    cmd = [python, "train.py", "--train", str(train_csv), "--predict", str(predict_csv), "--out", str(out_csv)]
    log.write("$ " + " ".join(cmd) + "\n")
    log.flush()
    p = subprocess.run(cmd, cwd=str(agent_dir), stdout=log, stderr=subprocess.STDOUT, timeout=TRAIN_TIMEOUT_S)
    if p.returncode != 0:
        raise RuntimeError(f"train.py exited with {p.returncode}")
    if not out_csv.exists():
        raise RuntimeError(f"train.py did not write {out_csv}")
    pred = pd.read_csv(out_csv)
    if not {"PassengerId", "Transported"} <= set(pred.columns):
        raise RuntimeError("prediction file must have columns PassengerId,Transported")
    if pred["PassengerId"].isna().any():
        raise RuntimeError("prediction contains missing PassengerId")
    pred = pred.drop_duplicates("PassengerId", keep="first")
    return pred


def aligned(pred: pd.DataFrame, truth: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    t = truth[["PassengerId", "Transported"]].copy()
    t["PassengerId"] = t["PassengerId"].astype(str)
    p = pred[["PassengerId", "Transported"]].copy()
    p["PassengerId"] = p["PassengerId"].astype(str)
    m = t.merge(p, on="PassengerId", how="left", suffixes=("_true", "_pred"))
    if m["Transported_pred"].isna().any():
        n_miss = int(m["Transported_pred"].isna().sum())
        raise RuntimeError(f"missing predictions for {n_miss} ids")
    return to_bool(m["Transported_pred"]), labels_to_bool(m["Transported_true"]), m["PassengerId"].to_numpy()


def group_folds(df: pd.DataFrame, n_splits: int, seed: int) -> np.ndarray:
    groups = df["PassengerId"].astype(str).str.split("_").str[0]
    y = labels_to_bool(df["Transported"]).astype(int)
    folds = np.empty(len(df), dtype=int)
    dummy = np.zeros(len(df))
    sgkf = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    for k, (_, va) in enumerate(sgkf.split(dummy, y, groups)):
        folds[va] = k
    return folds


def poll_kaggle_score(message: str, log, timeout_s: int = 600) -> tuple[float, float | None]:
    deadline = time.time() + timeout_s
    last_status = ""
    while time.time() < deadline:
        time.sleep(15)
        q = subprocess.run(
            ["kaggle", "competitions", "submissions", "-c", COMP, "--csv"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        log.write(q.stdout + q.stderr + "\n")
        log.flush()
        if q.returncode != 0:
            last_status = q.stderr.strip()[:200]
            continue
        rows = list(csv.DictReader(io.StringIO(q.stdout)))
        mine = [x for x in rows if x.get("description") == message]
        if not mine:
            last_status = "submission not listed yet"
            continue
        row = mine[0]
        status = (row.get("status") or "")
        last_status = status
        if "complete" in status.lower():
            pub = row.get("publicScore") or row.get("publicScoreExact") or ""
            priv = row.get("privateScore") or row.get("privateScoreExact") or ""
            if pub == "":
                raise RuntimeError("kaggle status complete but publicScore empty")
            private_score = float(priv) if priv not in ("", None) else None
            return float(pub), private_score
        if "error" in status.lower() or "fail" in status.lower():
            raise RuntimeError(f"kaggle submission failed: {status}")
    raise RuntimeError(f"submission accepted but no public score returned in time (last status={last_status!r})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent-dir", default=None)
    ap.add_argument("--seedset", default="quick", choices=["quick", "validation", "final"])
    ap.add_argument("--out", default=None)
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--message", default="")
    a = ap.parse_args()

    if a.agent_dir:
        agent_dir = Path(a.agent_dir).resolve()
    else:
        cwd = Path.cwd().resolve()
        agent_dir = cwd if (cwd / "train.py").exists() else TASK_DIR

    out = Path(a.out).resolve() if a.out else (agent_dir / f"metrics.{a.seedset}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="st-auto-eval-"))
    t0 = time.time()
    metrics: dict = {
        "seedset": a.seedset,
        "agent_dir": str(agent_dir),
        "metric": "accuracy",
        "higher_is_better": True,
        "score": None,
    }
    log = open(out.with_suffix(".log"), "w", encoding="utf-8")
    rc = 0
    try:
        train_path = agent_dir / "data" / "train.csv"
        if not train_path.exists():
            raise RuntimeError(f"missing {train_path}")
        public = pd.read_csv(train_path)
        if a.seedset == "quick":
            folds = group_folds(public, N_FOLDS, SEED)
            scores = []
            for k in range(N_FOLDS):
                tr, va = public[folds != k], public[folds == k]
                tr.to_csv(work / f"tr{k}.csv", index=False)
                va.drop(columns=["Transported"]).to_csv(work / f"va{k}.csv", index=False)
                pred = run_train(
                    agent_dir, a.python, work / f"tr{k}.csv", work / f"va{k}.csv", work / f"pred{k}.csv", log
                )
                p, t, _ = aligned(pred, va)
                scores.append(float((p == t).mean()))
            mean = float(np.mean(scores))
            std = float(np.std(scores, ddof=0))
            metrics.update(
                score=round(mean, 5),
                fold_scores=[round(s, 5) for s in scores],
                score_std=round(std, 5),
                score_sem=round(std / math.sqrt(N_FOLDS), 5),
                n=int(len(public)),
            )
        elif a.seedset == "validation":
            if not PRIVATE.exists():
                raise RuntimeError("hidden holdout missing; run prepare.py in the task pack")
            hold = pd.read_csv(PRIVATE)
            hold.drop(columns=["Transported"]).to_csv(work / "hold_x.csv", index=False)
            pred = run_train(
                agent_dir, a.python, train_path, work / "hold_x.csv", work / "pred.csv", log
            )
            p, t, ids = aligned(pred, hold)
            correct = (p == t).astype(float)
            std = float(correct.std())
            n = int(len(correct))
            metrics.update(
                score=round(float(correct.mean()), 5),
                n=n,
                score_std=round(std, 5),
                score_sem=round(std / math.sqrt(n), 5),
                per_item=[{"id": str(i), "value": float(c)} for i, c in zip(ids, correct)],
                score_transform="mean",
            )
        else:
            if not PRIVATE.exists():
                raise RuntimeError("hidden holdout missing; run prepare.py in the task pack")
            hold = pd.read_csv(PRIVATE)
            full = pd.concat([public, hold], ignore_index=True)
            full = full.drop_duplicates("PassengerId", keep="first")
            full.to_csv(work / "full.csv", index=False)
            test_path = agent_dir / "data" / "test.csv"
            ss_path = agent_dir / "data" / "sample_submission.csv"
            if not test_path.exists():
                raise RuntimeError(f"missing {test_path}")
            pred = run_train(
                agent_dir, a.python, work / "full.csv", test_path, work / "submission.csv", log
            )
            ss = pd.read_csv(ss_path) if ss_path.exists() else pd.read_csv(test_path)
            ids = ss["PassengerId"].astype(str)
            pred_map = dict(zip(pred["PassengerId"].astype(str), to_bool(pred["Transported"])))
            missing = [i for i in ids if i not in pred_map]
            if missing:
                raise RuntimeError(f"missing predictions for {len(missing)} test ids")
            sub = pd.DataFrame({"PassengerId": ids, "Transported": [bool(pred_map[i]) for i in ids]})
            sub_path = agent_dir / "submission.csv"
            sub.to_csv(sub_path, index=False)
            msg = a.message or f"pi-rsi {agent_dir.name} {int(time.time())}"
            r = subprocess.run(
                ["kaggle", "competitions", "submit", "-c", COMP, "-f", str(sub_path), "-m", msg],
                capture_output=True,
                text=True,
                timeout=300,
            )
            log.write(r.stdout + r.stderr + "\n")
            log.flush()
            if r.returncode != 0:
                raise RuntimeError(f"kaggle submit failed: {(r.stderr or r.stdout).strip()[:300]}")
            score, private_score = poll_kaggle_score(msg, log)
            metrics.update(score=score, n=int(len(sub)), submission=str(sub_path), message=msg)
            if private_score is not None:
                metrics["private_score"] = private_score
    except Exception as e:
        metrics.update(score=None, error=f"{type(e).__name__}: {e}")
        log.write(f"ERROR: {metrics['error']}\n")
        print(f"EVAL ERROR: {metrics['error']} (log {out.with_suffix('.log')})", file=sys.stderr)
        rc = 1
    finally:
        metrics["elapsed_s"] = round(time.time() - t0, 1)
        log.close()
        shutil.rmtree(work, ignore_errors=True)
        out.write_text(json.dumps(metrics, indent=1) + "\n")
    if rc == 0 and not a.quiet:
        extra = f" folds={metrics.get('fold_scores')}" if a.seedset == "quick" else ""
        print(
            f"[{a.seedset}] accuracy={metrics['score']:.5f} (higher is better) "
            f"n={metrics.get('n')}{extra} elapsed={metrics['elapsed_s']}s -> {out}"
        )
    return rc


if __name__ == "__main__":
    sys.exit(main())
