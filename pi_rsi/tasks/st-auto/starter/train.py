#!/usr/bin/env python3
"""Entry point required by the evaluator:

    python train.py --train <labeled.csv> --predict <features.csv> --out <pred.csv>

Starting point: logistic regression on a few numeric spend features plus age and CryoSleep.
Keep the CLI contract and the output columns PassengerId,Transported (True/False).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.features import basic_features, labels_to_bool
from src.model import LogisticModel


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", required=True)
    ap.add_argument("--predict", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    train = pd.read_csv(a.train)
    predict = pd.read_csv(a.predict)
    if "Transported" not in train.columns:
        raise SystemExit("labeled file must contain Transported")
    x_train, x_pred = basic_features(train, predict)
    y = labels_to_bool(train["Transported"])
    model = LogisticModel().fit(x_train, y)
    pred = model.predict(x_pred)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    out = pd.DataFrame({"PassengerId": predict["PassengerId"], "Transported": pred})
    # Match sample_submission: True/False strings, not 0/1.
    out["Transported"] = out["Transported"].map({True: "True", False: "False"})
    out.to_csv(a.out, index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
