#!/usr/bin/env python3
"""Download (if needed) and split the House Prices data.

- data/raw/            Kaggle files (downloaded with the kaggle CLI; requires accepting the competition rules once)
- starter/data/train.csv   public labeled part (80%), visible to the agent
- starter/data/test.csv    Kaggle test features (no labels), visible to the agent
- private/holdout.csv   hidden 20% of the labeled data (features + SalePrice), never copied into a worktree
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
RAW = HERE / "data" / "raw"
COMP = "house-prices-advanced-regression-techniques"
SEED = 20260910
HOLDOUT_FRAC = 0.2


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    if not (RAW / "train.csv").exists():
        subprocess.run(["kaggle", "competitions", "download", "-c", COMP, "-p", str(RAW)], check=True)
        subprocess.run(["unzip", "-oq", str(RAW / f"{COMP}.zip"), "-d", str(RAW)], check=True)
    train = pd.read_csv(RAW / "train.csv")
    rng = np.random.RandomState(SEED)
    # stratify on log-price deciles so the hidden split mirrors the price distribution
    dec = pd.qcut(np.log1p(train["SalePrice"]), 10, labels=False)
    hold_idx = []
    for d in sorted(dec.unique()):
        idx = train.index[dec == d].to_numpy()
        rng.shuffle(idx)
        k = int(round(len(idx) * HOLDOUT_FRAC))
        hold_idx.extend(idx[:k].tolist())
    hold_mask = train.index.isin(hold_idx)
    public, holdout = train[~hold_mask], train[hold_mask]
    (HERE / "starter" / "data").mkdir(parents=True, exist_ok=True)
    (HERE / "private").mkdir(parents=True, exist_ok=True)
    public.to_csv(HERE / "starter" / "data" / "train.csv", index=False)
    holdout.to_csv(HERE / "private" / "holdout.csv", index=False)
    pd.read_csv(RAW / "test.csv").to_csv(HERE / "starter" / "data" / "test.csv", index=False)
    pd.read_csv(RAW / "sample_submission.csv").to_csv(HERE / "starter" / "data" / "sample_submission.csv", index=False)
    (HERE / "docs").mkdir(exist_ok=True)
    (HERE / "docs" / "data_description.txt").write_text((RAW / "data_description.txt").read_text(encoding="utf-8", errors="replace"))
    print(f"public train {len(public)} rows, hidden holdout {len(holdout)} rows, test {sum(1 for _ in open(RAW / 'test.csv')) - 1} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
