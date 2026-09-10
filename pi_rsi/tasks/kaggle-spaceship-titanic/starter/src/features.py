"""Feature construction. The starter uses spend columns, age and CryoSleep only."""
from __future__ import annotations

import numpy as np
import pandas as pd

SPEND = ["RoomService", "FoodCourt", "ShoppingMall", "Spa", "VRDeck"]


def basic_features(train: pd.DataFrame, predict: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    def build(df: pd.DataFrame, med: pd.Series | None = None) -> pd.DataFrame:
        out = pd.DataFrame(index=df.index)
        for c in SPEND:
            out[c] = np.log1p(df[c].fillna(0.0))
        out["TotalSpend"] = np.log1p(df[SPEND].fillna(0.0).sum(axis=1))
        out["Age"] = df["Age"]
        out["CryoSleep"] = df["CryoSleep"].map({True: 1.0, False: 0.0, "True": 1.0, "False": 0.0})
        return out

    xt = build(train)
    xp = build(predict)
    med = xt.median()
    return xt.fillna(med).to_numpy(dtype=float), xp.fillna(med).to_numpy(dtype=float)
