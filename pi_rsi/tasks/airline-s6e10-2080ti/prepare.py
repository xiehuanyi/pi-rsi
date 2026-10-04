#!/usr/bin/env python3
"""One-time deterministic split preparation; existing frozen output is verified, not rewritten."""
import os
for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[key] = '8'
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parent
SEED = 20261004
TARGET = 'satisfaction'
FEATURES = ['Age', 'Flight Distance', 'Inflight wifi service',
            'Departure/Arrival time convenient', 'Ease of Online booking', 'Gate location',
            'Food and drink', 'Online boarding', 'Seat comfort', 'Inflight entertainment',
            'On-board service', 'Leg room service', 'Baggage handling', 'Checkin service',
            'Cleanliness', 'Departure Delay in Minutes', 'Arrival Delay in Minutes',
            'Gender', 'Customer Type', 'Type of Travel', 'Class']


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    manifest_path = ROOT / 'private/manifest.json'
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        for rel, info in manifest['files'].items():
            if sha(ROOT / rel) != info['sha256']:
                raise RuntimeError(f'Frozen file changed: {rel}; do not regenerate splits')
        public = json.loads((ROOT / 'eval/data_manifest.json').read_text())
        if public != {k: manifest[k] for k in ('protocol', 'seed', 'target_mapping', 'columns', 'files', 'splits')}:
            raise RuntimeError('Frozen public manifest changed')
        print('Existing frozen preparation verified; no split rewritten.')
        return
    if (ROOT / 'starter/data/train_pool.csv').exists():
        raise RuntimeError('Partial preparation exists; inspect it rather than silently overwriting')
    raw = ROOT / 'data/raw'
    train = pd.read_csv(raw / 'train.csv')
    test = pd.read_csv(raw / 'test.csv')
    sample = pd.read_csv(raw / 'sample_submission.csv')
    if train.columns.tolist() != ['id'] + FEATURES + [TARGET]:
        raise ValueError(f'Unexpected train columns: {train.columns.tolist()}')
    assert test.columns.tolist() == ['id'] + FEATURES
    assert sample.columns.tolist() == ['id', TARGET]
    assert (len(train), len(test), len(sample)) == (699635, 299844, 299844)
    assert train['id'].notna().all() and train['id'].is_unique
    assert test['id'].notna().all() and test['id'].is_unique
    assert sample['id'].equals(test['id'])
    assert set(train.id).isdisjoint(set(test.id))
    observed = sorted(train[TARGET].dropna().unique().tolist())
    if train[TARGET].isna().any() or observed != [0, 1]:
        raise ValueError(f'Expected observed numeric binary labels 0/1; found {observed}')
    # The competition sample already uses probabilities; no inverted/string mapping.
    train[TARGET] = train[TARGET].astype('int8')
    pool, hold = train_test_split(np.arange(len(train)), train_size=0.70,
                                 stratify=train[TARGET], random_state=SEED)
    validation, final = train_test_split(hold, test_size=0.5,
                                       stratify=train.iloc[hold][TARGET], random_state=SEED)
    quick_train, rest = train_test_split(pool, train_size=50000,
                                       stratify=train.iloc[pool][TARGET], random_state=SEED)
    quick_dev, _ = train_test_split(rest, train_size=10000,
                                  stratify=train.iloc[rest][TARGET], random_state=SEED)
    sets = {'train_pool': pool, 'validation': validation, 'final': final,
            'quick_train': quick_train, 'quick_dev': quick_dev}
    assert set(pool).isdisjoint(hold)
    assert set(validation).isdisjoint(final)
    assert set(quick_train).isdisjoint(quick_dev)
    files = {}

    def save(frame, rel):
        p = ROOT / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(p, index=False, lineterminator='\n')
        files[rel] = {'sha256': sha(p), 'rows': len(frame)}

    save(train.iloc[pool], 'starter/data/train_pool.csv')
    # The evaluator's immutable canonical training copy defeats accidental worker edits.
    save(train.iloc[pool], 'private/train_pool.csv')
    save(train.iloc[quick_train], 'starter/data/quick_train.csv')
    save(train.iloc[quick_dev], 'starter/data/quick_dev.csv')
    for level in ('validation', 'final'):
        rows = train.iloc[sets[level]]
        save(rows.drop(columns=TARGET), f'private/{level}_features.csv')
        save(rows[['id', TARGET]], f'private/{level}_labels.csv')
    for name in ('test.csv', 'sample_submission.csv'):
        p = ROOT / 'starter/data' / name
        shutil.copyfile(raw / name, p)
        files[f'starter/data/{name}'] = {'sha256': sha(p), 'rows': len(test)}
    for name in ('train.csv', 'test.csv', 'sample_submission.csv'):
        files[f'data/raw/{name}'] = {'sha256': sha(raw / name),
                                  'rows': len(train) if name == 'train.csv' else len(test)}
    splits = {}
    for name, idx in sets.items():
        splits[name] = {'n': len(idx),
                       'positive': int(train.iloc[idx][TARGET].sum()),
                       'ordered_ids_sha256': hashlib.sha256(
                           train.iloc[idx]['id'].to_numpy(dtype='<i8').tobytes()).hexdigest()}
    manifest = {'protocol': 'airline-s6e10-stratified-v1', 'seed': SEED,
                'target_mapping': {'0': 0, '1': 1}, 'columns': train.columns.tolist(),
                'observed_target_counts': {str(k): int(v) for k, v in train[TARGET].value_counts().items()},
                'files': files, 'splits': splits,
                'versions': {'numpy': np.__version__, 'pandas': pd.__version__,
                             'sklearn': __import__('sklearn').__version__}}
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    # Hashes/counts are public; no held-out row IDs, features or individual labels.
    public = {k: manifest[k] for k in ('protocol', 'seed', 'target_mapping', 'columns', 'files', 'splits')}
    (ROOT / 'eval').mkdir(exist_ok=True)
    (ROOT / 'eval/data_manifest.json').write_text(json.dumps(public, indent=2) + '\n')
    print(json.dumps({'observed_target_counts': manifest['observed_target_counts'], 'splits': splits}, indent=2))


if __name__ == '__main__':
    main()
