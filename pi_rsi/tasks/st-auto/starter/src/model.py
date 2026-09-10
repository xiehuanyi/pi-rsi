"""Models. The starter fits a standardized logistic regression."""
from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


class LogisticModel:
    def __init__(self, c: float = 1.0):
        self.pipe = make_pipeline(
            StandardScaler(),
            LogisticRegression(C=c, max_iter=1000, random_state=0),
        )

    def fit(self, x: np.ndarray, y: np.ndarray) -> "LogisticModel":
        self.pipe.fit(x, y.astype(int))
        return self

    def predict(self, x: np.ndarray) -> np.ndarray:
        return self.pipe.predict(x).astype(bool)
