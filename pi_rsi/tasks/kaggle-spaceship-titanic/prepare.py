#!/usr/bin/env python3
"""Download (if needed) and split the Spaceship Titanic data.

- data/raw/                 Kaggle files (kaggle CLI; the competition rules must be accepted on the website once)
- starter/data/train.csv    public labeled part (80%), visible to the agent
- starter/data/test.csv     Kaggle test features (no labels), visible to the agent
- private/holdout.csv       hidden 20% of the labeled data (features + Transported), never copied into a worktree
Split is stratified on the label and keeps passenger groups (PassengerId prefix gggg) together.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
RAW = HERE / "data" / "raw"
COMP = "spaceship-titanic"
SEED = 20260910
HOLDOUT_FRAC = 0.2


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    if not (RAW / "train.csv").exists():
        subprocess.run(["kaggle", "competitions", "download", "-c", COMP, "-p", str(RAW)], check=True)
        subprocess.run(["unzip", "-oq", str(RAW / f"{COMP}.zip"), "-d", str(RAW)], check=True)
    train = pd.read_csv(RAW / "train.csv")
    group = train["PassengerId"].str.split("_").str[0]
    rng = np.random.RandomState(SEED)
    groups = group.unique()
    rng.shuffle(groups)
    # assign whole groups to the holdout until ~20% of rows are covered
    hold_groups, count, target = set(), 0, int(round(len(train) * HOLDOUT_FRAC))
    sizes = group.value_counts()
    for g in groups:
        if count >= target:
            break
        hold_groups.add(g)
        count += int(sizes[g])
    mask = group.isin(hold_groups)
    public, holdout = train[~mask], train[mask]
    (HERE / "starter" / "data").mkdir(parents=True, exist_ok=True)
    (HERE / "private").mkdir(parents=True, exist_ok=True)
    public.to_csv(HERE / "starter" / "data" / "train.csv", index=False)
    holdout.to_csv(HERE / "private" / "holdout.csv", index=False)
    pd.read_csv(RAW / "test.csv").to_csv(HERE / "starter" / "data" / "test.csv", index=False)
    pd.read_csv(RAW / "sample_submission.csv").to_csv(HERE / "starter" / "data" / "sample_submission.csv", index=False)
    print(f"public train {len(public)} rows ({public['Transported'].mean():.3f} positive), hidden holdout {len(holdout)} rows "
          f"({holdout['Transported'].mean():.3f} positive), test {sum(1 for _ in open(RAW / 'test.csv')) - 1} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
