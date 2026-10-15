#!/usr/bin/env python3
"""GPU CatBoost baseline; the frozen evaluator owns scoring and holdout labels."""
import os
for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[key] = '8'
import argparse
import json
import time
from pathlib import Path

import pandas as pd
from catboost import CatBoostClassifier, Pool
from src.features import CATEGORICAL, TARGET, make_features
from src.hardware import verify_gpu


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--train', required=True)
    ap.add_argument('--predict', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--seed', type=int, default=20261004)
    ap.add_argument('--threads', type=int, default=8)
    ap.add_argument('--budget', type=float, default=60)
    ap.add_argument('--model-out', default=None)
    args = ap.parse_args()
    if not 1 <= args.threads <= 8:
        raise ValueError('CPU threads must be between 1 and 8')
    start = time.monotonic()
    gpu = verify_gpu()
    train = pd.read_csv(args.train)
    predict = pd.read_csv(args.predict)
    if TARGET in predict.columns:
        raise ValueError('Prediction input must not contain target')
    if set(train[TARGET].unique()) != {0, 1}:
        raise ValueError('Training target must be mapped to 0/1')
    X = make_features(train)
    Xp = make_features(predict)
    if X.columns.tolist() != Xp.columns.tolist():
        raise ValueError('Feature schema mismatch')
    train_pool = Pool(X, label=train[TARGET], cat_features=CATEGORICAL)
    pred_pool = Pool(Xp, cat_features=CATEGORICAL)
    model = CatBoostClassifier(iterations=400, depth=6, learning_rate=0.08,
                               loss_function='Logloss', random_seed=args.seed,
                               task_type='GPU', devices='0', thread_count=args.threads,
                               boosting_type='Plain', one_hot_max_size=10,
                               l2_leaf_reg=3.0, gpu_ram_part=0.85,
                               allow_writing_files=False, verbose=100)
    fit_start = time.monotonic()
    # No early stopping: neither official nor quick evaluation labels are used to fit.
    model.fit(train_pool)
    fit_seconds = time.monotonic() - fit_start
    prob = model.predict_proba(pred_pool, thread_count=args.threads)[:, 1]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({'id': predict['id'], TARGET: prob}).to_csv(out, index=False)
    artifact = Path(args.model_out) if args.model_out else out.with_suffix('.cbm')
    artifact.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(str(artifact))
    metadata = {'gpu': gpu, 'fit_elapsed_s': fit_seconds,
                'candidate_elapsed_s': time.monotonic() - start,
                'iterations': model.tree_count_, 'seed': args.seed,
                'train_n': len(train), 'predict_n': len(predict)}
    artifact.with_suffix('.metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(json.dumps(metadata), flush=True)


if __name__ == '__main__':
    main()
