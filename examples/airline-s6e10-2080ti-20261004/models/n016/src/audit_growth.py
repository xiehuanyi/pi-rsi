"""Audit public quick artifacts without fitting or consuming dev targets.

Run after the registered block: python -m src.audit_growth
No official artifacts or labels are opened. Reload inference is CPU-only.
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


def audit_quick(run_dir, policy):
    metrics = json.loads((run_dir / 'metrics.json').read_text())
    assert metrics['level'] == 'quick' and metrics['score'] is not None
    assert metrics['gpu']['physical_index'] == 1
    assert metrics['gpu']['logical_device'] == 0
    assert metrics['gpu']['uuid'] == 'GPU-2c54fc50-8962-5ef4-a42f-45752aedef9d'
    artifact = run_dir / 'model.cbm'
    alias = run_dir / 'model.pt'
    assert sha(artifact) == sha(alias) == metrics['model_sha256']
    predictions = run_dir / 'predictions.csv'
    assert sha(predictions) == metrics['prediction_sha256']
    output = pd.read_csv(predictions, dtype={'id': 'string'})
    features = pd.read_csv('data/quick_dev.csv', usecols=lambda c: c != TARGET,
                           dtype={'id': 'string'})
    assert output.columns.tolist() == ['id', TARGET]
    assert output['id'].equals(features['id']) and output['id'].is_unique
    p = output[TARGET].to_numpy()
    assert np.isfinite(p).all() and ((p >= 0) & (p <= 1)).all()
    X = make_features(features, 'raw')
    assert len(X.columns) == 21 and not {'id', TARGET, 'service_mean'}.intersection(X)
    report = metrics['candidate_report']
    assert report['feature_mode'] == 'raw' and report['feature_names'] == X.columns.tolist()
    model = CatBoostClassifier()
    model.load_model(str(artifact), format='cbm')
    assert model.feature_names_ == X.columns.tolist()
    assert model.get_cat_feature_indices() == [X.columns.get_loc(c) for c in CATEGORICAL]
    params = model.get_all_params()
    for key, value in {'iterations': 400, 'depth': 8, 'l2_leaf_reg': 10,
                       'grow_policy': policy, 'boosting_type': 'Plain',
                       'loss_function': 'Logloss', 'task_type': 'GPU',
                       'one_hot_max_size': 10, 'random_seed': 20261004}.items():
        assert params[key] == value, (key, params[key], value)
    assert np.isclose(params['learning_rate'], .08, rtol=0, atol=1e-8)
    if policy == 'Depthwise':
        assert params['min_data_in_leaf'] == 1
    else:
        assert 'min_data_in_leaf' not in report['model_params']
    pool = Pool(X, cat_features=CATEGORICAL)
    reloaded = model.predict_proba(pool, thread_count=8, task_type='CPU')[:, 1]
    np.testing.assert_allclose(reloaded, p, rtol=0, atol=1e-15)
    alias_model = CatBoostClassifier()
    alias_model.load_model(str(alias), format='cbm')
    np.testing.assert_array_equal(reloaded, alias_model.predict_proba(
        pool, thread_count=8, task_type='CPU')[:, 1])
    leaves = model.get_tree_leaf_counts()
    assert len(leaves) == 400 and np.all(leaves <= 256)
    return {'effective_model_params': params, 'model_bytes': artifact.stat().st_size,
            'model_sha256': sha(artifact), 'prediction_sha256': sha(predictions),
            'reload_max_abs_error': float(np.max(np.abs(reloaded - p))),
            'ordered_ids': True, 'finite_unit_interval': True, 'alias_identical': True,
            'leaf_counts': leaves.tolist(), 'total_leaves': int(leaves.sum()),
            'min_leaves': int(leaves.min()), 'max_leaves': int(leaves.max()),
            'inference_device': 'CPU'}


def main():
    path = Path('runs/depthwise_designated')
    result = {'node': 'n016', 'level': 'quick', 'seed': 20261004,
              'failed_launches': [
                  {'trial': 1, 'score': None, 'error': 'Queue-client import failed before submission'},
                  {'trial': 2, 'score': None, 'error': 'Wrong wrapper path; queue exit2 before evaluation'}],
              'designated': {'metrics': json.loads((path / 'metrics.json').read_text()),
                             'audit': audit_quick(path, 'Depthwise')}}
    historical = json.loads(Path('src/raw_ablation_results.json').read_text())
    result['historical_control'] = {
        'node': 'n014', 'source': 'src/raw_ablation_results.json',
        'scope': 'Historical fixed-setting quick reference, not fresh matched control',
        'metrics': historical['raw_metrics'], 'audit': historical['audit']}
    a = historical['audit']['effective_model_params']
    b = result['designated']['audit']['effective_model_params']
    result['effective_parameter_differences'] = {
        k: {'A': a.get(k), 'B': b.get(k)} for k in sorted(a.keys() | b.keys())
        if a.get(k) != b.get(k)}
    result['B_minus_historical_A'] = (result['designated']['metrics']['score']
                                     - historical['raw_metrics']['score'])
    result['historical_quick_practical_screen'] = result['B_minus_historical_A'] >= .0002
    result['source_sha256'] = {str(p): sha(p) for p in (
        Path('train.py'), Path('src/config.py'), Path('src/features.py'))}
    result['limitations'] = [
        'Two failed launches and one successful fixed-seed fit; fresh A/support100 unavailable.',
        'GPU variation unquantified; quick is not independent/full-pool confirmation.',
        'Policy defaults audited; equal depth/rounds does not equalize leaves or compute.',
        'AUC does not identify passenger-partition mechanism; no official worker evaluation.']
    # Keep evidence below the per-file line ceiling; each top-level packet is one line.
    packets = [json.dumps(k) + ': ' + json.dumps(v) for k, v in result.items()]
    Path('src/growth_results.json').write_text('{\n  ' + ',\n  '.join(packets) + '\n}\n')
    print(json.dumps({'B_minus_historical_A': result['B_minus_historical_A'],
                      'effective_parameter_differences': result['effective_parameter_differences'],
                      'audits': 'passed'}))


if __name__ == '__main__':
    main()
