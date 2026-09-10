"""Feature construction. The starter uses a few numeric columns only."""
from __future__ import annotations

import numpy as np
import pandas as pd

NUMERIC = ["OverallQual", "GrLivArea", "GarageCars", "TotalBsmtSF", "FullBath", "YearBuilt", "YearRemodAdd", "LotArea"]


def basic_numeric_features(train: pd.DataFrame, predict: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    cols = [c for c in NUMERIC if c in train.columns and c in predict.columns]
    med = train[cols].median()
    xt = train[cols].fillna(med).to_numpy(dtype=float)
    xp = predict[cols].fillna(med).to_numpy(dtype=float)
    return xt, xp
