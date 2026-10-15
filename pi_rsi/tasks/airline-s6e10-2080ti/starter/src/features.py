"""Baseline: raw non-ID columns, native CatBoost categories; no learned preprocessing."""
import pandas as pd

TARGET = 'satisfaction'
CATEGORICAL = ['Gender', 'Customer Type', 'Type of Travel', 'Class']


def make_features(frame):
    X = frame.drop(columns=['id', TARGET], errors='ignore').copy()
    for col in X.columns:
        if col in CATEGORICAL:
            X[col] = X[col].fillna('__MISSING__').astype(str)
        else:
            X[col] = pd.to_numeric(X[col], errors='raise').astype('float32')
    return X
