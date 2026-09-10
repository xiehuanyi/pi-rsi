"""Models. The starter fits ridge regression on log1p(target) with standardized inputs."""
from __future__ import annotations

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


class RidgeLogModel:
    def __init__(self, alpha: float = 10.0):
        self.pipe = make_pipeline(StandardScaler(), Ridge(alpha=alpha))

    def fit(self, x: np.ndarray, y: np.ndarray) -> "RidgeLogModel":
        self.pipe.fit(x, np.log1p(y))
        return self

    def predict(self, x: np.ndarray) -> np.ndarray:
        return np.expm1(self.pipe.predict(x))
