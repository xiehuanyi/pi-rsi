"""Feature construction. The starter uses spend columns, age and CryoSleep only."""
from __future__ import annotations

import numpy as np
import pandas as pd

SPEND = ["RoomService", "FoodCourt", "ShoppingMall", "Spa", "VRDeck"]


def labels_to_bool(s: pd.Series) -> np.ndarray:
    if pd.api.types.is_bool_dtype(s):
        return s.to_numpy()
    if pd.api.types.is_numeric_dtype(s):
        return (pd.to_numeric(s, errors="coerce") >= 0.5).to_numpy()
    return s.astype(str).str.strip().str.lower().isin(["true", "1", "1.0", "yes"]).to_numpy()


def basic_features(train: pd.DataFrame, predict: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    def build(df: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame(index=df.index)
        for c in SPEND:
            if c in df.columns:
                out[c] = np.log1p(pd.to_numeric(df[c], errors="coerce").fillna(0.0))
            else:
                out[c] = 0.0
        spend = pd.concat([pd.to_numeric(df[c], errors="coerce").fillna(0.0) for c in SPEND if c in df.columns], axis=1)
        out["TotalSpend"] = np.log1p(spend.sum(axis=1) if not spend.empty else 0.0)
        out["Age"] = pd.to_numeric(df["Age"], errors="coerce") if "Age" in df.columns else np.nan
        cryo = df["CryoSleep"] if "CryoSleep" in df.columns else pd.Series(np.nan, index=df.index)
        out["CryoSleep"] = cryo.map({True: 1.0, False: 0.0, "True": 1.0, "False": 0.0})
        return out

    xt = build(train)
    xp = build(predict)
    med = xt.median(numeric_only=True)
    return xt.fillna(med).to_numpy(dtype=float), xp.fillna(med).to_numpy(dtype=float)
