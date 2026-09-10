#!/usr/bin/env python3
"""Build the public/hidden split from already-downloaded Kaggle files.

- data/raw/                    official Kaggle CSVs (do not re-download)
- starter/data/train.csv       public labeled part (~80%), visible to workers
- starter/data/test.csv        Kaggle test features (no labels), visible to workers
- starter/data/sample_submission.csv
- private/holdout.csv          hidden ~20% of labeled rows (features + Transported)

Split is group-aware (PassengerId prefix gggg stays together) and stratified on
Transported via StratifiedGroupKFold. Holdout is fold 0 of a 5-fold assignment.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold

HERE = Path(__file__).resolve().parent
RAW = HERE / "data" / "raw"
SEED = 20260910
N_SPLITS = 5


def to_bool(s: pd.Series) -> np.ndarray:
    if pd.api.types.is_bool_dtype(s):
        return s.to_numpy()
    if pd.api.types.is_numeric_dtype(s):
        return (pd.to_numeric(s, errors="coerce") >= 0.5).to_numpy()
    return s.astype(str).str.strip().str.lower().isin(["true", "1", "1.0", "yes"]).to_numpy()


def main() -> int:
    for name in ("train.csv", "test.csv", "sample_submission.csv"):
        p = RAW / name
        if not p.exists():
            raise SystemExit(f"missing {p}; expected already-downloaded Kaggle files under data/raw/")

    train = pd.read_csv(RAW / "train.csv")
    if "PassengerId" not in train.columns or "Transported" not in train.columns:
        raise SystemExit("train.csv must have PassengerId and Transported")

    groups = train["PassengerId"].astype(str).str.split("_").str[0]
    y = to_bool(train["Transported"]).astype(int)
    dummy = np.zeros(len(train))
    sgkf = StratifiedGroupKFold(n_splits=N_SPLITS, shuffle=True, random_state=SEED)
    tr_idx, ho_idx = next(sgkf.split(dummy, y, groups))
    public, holdout = train.iloc[tr_idx].copy(), train.iloc[ho_idx].copy()

    pub_g = set(public["PassengerId"].astype(str).str.split("_").str[0])
    ho_g = set(holdout["PassengerId"].astype(str).str.split("_").str[0])
    overlap_g = pub_g & ho_g
    overlap_id = set(public["PassengerId"]) & set(holdout["PassengerId"])
    if overlap_g or overlap_id:
        raise SystemExit(f"leakage in split: group overlap={len(overlap_g)} id overlap={len(overlap_id)}")

    starter_data = HERE / "starter" / "data"
    private = HERE / "private"
    starter_data.mkdir(parents=True, exist_ok=True)
    private.mkdir(parents=True, exist_ok=True)
    public.to_csv(starter_data / "train.csv", index=False)
    holdout.to_csv(private / "holdout.csv", index=False)
    pd.read_csv(RAW / "test.csv").to_csv(starter_data / "test.csv", index=False)
    pd.read_csv(RAW / "sample_submission.csv").to_csv(starter_data / "sample_submission.csv", index=False)

    pub_pos = float(to_bool(public["Transported"]).mean())
    ho_pos = float(to_bool(holdout["Transported"]).mean())
    n_test = sum(1 for _ in open(RAW / "test.csv", encoding="utf-8")) - 1
    print(
        f"public train {len(public)} rows ({pub_pos:.3f} positive, {len(pub_g)} groups), "
        f"hidden holdout {len(holdout)} rows ({ho_pos:.3f} positive, {len(ho_g)} groups), "
        f"test {n_test} rows, group overlap {len(overlap_g)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
