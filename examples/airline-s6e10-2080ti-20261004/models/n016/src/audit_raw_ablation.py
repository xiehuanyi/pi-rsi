"""Non-fitting audit of n014 quick artifacts; never opens official artifacts.

Run: python -m src.audit_raw_ablation
Uses CPU inference only on an already fitted model and public quick-dev features.
"""
import os
for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[key] = '8'
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, Pool

from src.features import CATEGORICAL, TARGET, make_features


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_quick(run_dir):
    metrics = json.loads((run_dir / 'metrics.json').read_text())
    assert metrics['level'] == 'quick' and metrics['score'] is not None
    assert metrics['gpu']['physical_index'] == 1
    assert metrics['gpu']['logical_device'] == 0
    assert metrics['gpu']['uuid'] == 'GPU-2c54fc50-8962-5ef4-a42f-45752aedef9d'
    model_path = run_dir / 'model.cbm'
    alias = run_dir / 'model.pt'
    assert sha(model_path) == metrics['model_sha256'] == sha(alias)
    prediction_path = run_dir / 'predictions.csv'
    assert sha(prediction_path) == metrics['prediction_sha256']
    prediction = pd.read_csv(prediction_path, dtype={'id': 'string'})
    # Do not consume development targets, even for this inference-only audit.
    features = pd.read_csv('data/quick_dev.csv', usecols=lambda c: c != TARGET,
                           dtype={'id': 'string'})
    assert prediction.columns.tolist() == ['id', TARGET]
    assert prediction['id'].equals(features['id']) and prediction['id'].is_unique
    probabilities = prediction[TARGET].to_numpy()
    assert np.isfinite(probabilities).all()
    assert ((probabilities >= 0) & (probabilities <= 1)).all()
    raw = make_features(features)
    mean = make_features(features, 'mean')
    assert len(raw.columns) == 21 and 'service_mean' not in raw
    assert mean.columns.tolist() == raw.columns.tolist() + ['service_mean']
    pd.testing.assert_frame_equal(raw, mean.drop(columns='service_mean'))
    assert not {'id', TARGET}.intersection(raw.columns)
    report = metrics['candidate_report']
    assert report['feature_mode'] == 'raw'
    assert report['feature_names'] == raw.columns.tolist()
    model = CatBoostClassifier()
    model.load_model(str(model_path), format='cbm')
    assert model.feature_names_ == raw.columns.tolist()
    assert model.get_cat_feature_indices() == [raw.columns.get_loc(c) for c in CATEGORICAL]
    params = model.get_all_params()
    expected = {'iterations': 400, 'depth': 8, 'l2_leaf_reg': 10,
                'grow_policy': 'SymmetricTree', 'boosting_type': 'Plain',
                'loss_function': 'Logloss', 'task_type': 'GPU',
                'one_hot_max_size': 10, 'random_seed': 20261004}
    for key, value in expected.items():
        assert params[key] == value, (key, params[key], value)
    assert np.isclose(params['learning_rate'], .08, rtol=0, atol=1e-8)
    pool = Pool(raw, cat_features=CATEGORICAL)
    reloaded = model.predict_proba(pool, thread_count=8, task_type='CPU')[:, 1]
    np.testing.assert_allclose(reloaded, probabilities, rtol=0, atol=1e-15)
    alias_model = CatBoostClassifier()
    alias_model.load_model(str(alias), format='cbm')
    np.testing.assert_array_equal(reloaded, alias_model.predict_proba(
        pool, thread_count=8, task_type='CPU')[:, 1])
    return {'model_sha256': sha(model_path), 'prediction_sha256': sha(prediction_path),
            'alias_sha256': sha(alias), 'feature_names': raw.columns.tolist(),
            'effective_model_params': params, 'model_bytes': model_path.stat().st_size,
            'reload_max_abs_error': float(np.max(np.abs(reloaded - probabilities))),
            'ordered_ids': True, 'finite_unit_interval': True,
            'raw_equals_mean_without_service_mean': True, 'inference_device': 'CPU'}


def main():
    run_dir = Path('runs/raw_designated')
    evidence = {'node': 'n014', 'level': 'quick', 'seed': 20261004,
                'raw_metrics': json.loads((run_dir / 'metrics.json').read_text()),
                'failed_attempts': [json.loads((Path('runs') / arm / 'metrics.json').read_text())
                                    for arm in ('mean_control', 'mean_control_repaired')],
                'audit': audit_quick(run_dir),
                'source_sha256': {str(p): sha(p) for p in (
                    Path('train.py'), Path('src/config.py'), Path('src/features.py'))}}
    historical = json.loads(Path('src/depth_results.json').read_text())
    mean = next(t for t in historical['trials'] if t['arm'] == 'C')
    evidence['historical_mean_reference'] = {
        'node': 'n008', 'level': 'quick', 'seed': historical['seed'],
        'score': mean['score'], 'source': 'src/depth_results.json',
        'scope': 'Historical unmatched reference, not a fresh control'}
    evidence['raw_minus_historical_mean'] = evidence['raw_metrics']['score'] - mean['score']
    evidence['limitations'] = [
        'Two control attempts failed before fitting; no fresh matched mean measurement.',
        'One successful fixed-seed raw fit; GPU non-bitwise variation is unquantified.',
        'No official worker evaluation; final remains sealed.',
        'No significance, equivalence or mechanistic inference from AUC differences.']
    Path('src/raw_ablation_results.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps({'audit': 'passed', 'score': evidence['raw_metrics']['score'],
                      'raw_minus_historical_mean': evidence['raw_minus_historical_mean'],
                      'reload_max_abs_error': evidence['audit']['reload_max_abs_error']}))


if __name__ == '__main__':
    main()
