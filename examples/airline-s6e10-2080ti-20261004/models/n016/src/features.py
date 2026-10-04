"""Raw CatBoost features plus optional deterministic, row-local service summaries."""
import numpy as np
import pandas as pd

TARGET = 'satisfaction'
CATEGORICAL = ['Gender', 'Customer Type', 'Type of Travel', 'Class']
# n014 designated ablation: remove only service_mean at n008 capacity.
# Optional historical summaries remain available for explicit control runs.
FEATURE_MODE = 'raw'
FEATURE_MODES = ('raw', 'mean', 'profile')
SERVICE_RATINGS = (
    'Inflight wifi service',
    'Departure/Arrival time convenient',
    'Ease of Online booking',
    'Gate location',
    'Food and drink',
    'Online boarding',
    'Seat comfort',
    'Inflight entertainment',
    'On-board service',
    'Leg room service',
    'Baggage handling',
    'Checkin service',
    'Cleanliness',
)
DIGITAL_RATINGS = ('Inflight wifi service', 'Ease of Online booking', 'Online boarding')
CABIN_RATINGS = (
    'Food and drink', 'Seat comfort', 'Inflight entertainment',
    'On-board service', 'Leg room service', 'Cleanliness',
)
SUMMARY_FEATURES = (
    'service_mean', 'service_std', 'service_range', 'service_low_count',
    'service_high_count', 'digital_minus_cabin',
)


def service_summaries(X, mode):
    """Equal-weight numeric summaries; zero is observed, not missing.

    No fitted state or aggregation across passengers. The prespecified groups
    are column-name heuristics, not validated latent service constructs.
    """
    if mode not in FEATURE_MODES:
        raise ValueError(f'Unknown feature mode: {mode}')
    result = pd.DataFrame(index=X.index)
    if mode == 'raw':
        return result
    ratings = X.loc[:, SERVICE_RATINGS].to_numpy(dtype=np.float64)
    result['service_mean'] = ratings.mean(axis=1)
    if mode == 'profile':
        result['service_std'] = ratings.std(axis=1, ddof=0)
        result['service_range'] = ratings.max(axis=1) - ratings.min(axis=1)
        result['service_low_count'] = (ratings <= 1).sum(axis=1)
        result['service_high_count'] = (ratings >= 4).sum(axis=1)
        digital = X.loc[:, DIGITAL_RATINGS].to_numpy(dtype=np.float64).mean(axis=1)
        cabin = X.loc[:, CABIN_RATINGS].to_numpy(dtype=np.float64).mean(axis=1)
        result['digital_minus_cabin'] = digital - cabin
    return result.astype('float32')


def make_features(frame, mode=None):
    mode = FEATURE_MODE if mode is None else mode
    X = frame.drop(columns=['id', TARGET], errors='ignore').copy()
    for col in X.columns:
        if col in CATEGORICAL:
            X[col] = X[col].fillna('__MISSING__').astype(str)
        else:
            X[col] = pd.to_numeric(X[col], errors='raise').astype('float32')
    return pd.concat([X, service_summaries(X, mode)], axis=1)
