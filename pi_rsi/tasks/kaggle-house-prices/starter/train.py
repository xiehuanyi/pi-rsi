#!/usr/bin/env python3
"""Entry point required by the evaluator:  python train.py --train X.csv --predict Y.csv --out pred.csv

Starting point: a ridge regression on a handful of numeric features with median imputation, fit on log1p(SalePrice).
Everything else (features, models, ensembling, tuning) is up to you; keep the CLI contract unchanged.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from src.features import basic_numeric_features
from src.model import RidgeLogModel


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", required=True)
    ap.add_argument("--predict", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    train = pd.read_csv(a.train)
    predict = pd.read_csv(a.predict)
    x_train, x_pred = basic_numeric_features(train, predict)
    model = RidgeLogModel(alpha=10.0)
    model.fit(x_train, train["SalePrice"].to_numpy())
    pred = model.predict(x_pred)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"Id": predict["Id"], "SalePrice": pred}).to_csv(a.out, index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
