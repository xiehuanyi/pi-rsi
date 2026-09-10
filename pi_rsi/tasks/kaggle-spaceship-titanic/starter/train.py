#!/usr/bin/env python3
"""Entry point required by the evaluator:  python train.py --train X.csv --predict Y.csv --out pred.csv

Starting point: logistic regression on a few numeric spend features plus CryoSleep. Keep the CLI contract and the
output columns PassengerId,Transported (True/False).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.features import basic_features
from src.model import LogisticModel


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", required=True)
    ap.add_argument("--predict", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    train = pd.read_csv(a.train)
    predict = pd.read_csv(a.predict)
    x_train, x_pred = basic_features(train, predict)
    model = LogisticModel().fit(x_train, train["Transported"].astype(bool).to_numpy())
    pred = model.predict(x_pred)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"PassengerId": predict["PassengerId"], "Transported": pred}).to_csv(a.out, index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
