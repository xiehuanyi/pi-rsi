#!/usr/bin/env python3
"""Designated raw GPU Depthwise CatBoost; frozen evaluator owns scoring."""
import os
for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[key] = '8'
import argparse
import json
import time
from pathlib import Path

import pandas as pd
from catboost import CatBoostClassifier, Pool
from src.features import CATEGORICAL, TARGET, FEATURE_MODE, FEATURE_MODES, make_features
from src.artifacts import copy_compatibility_alias
from src.config import (
    DEFAULT_ITERATIONS, DEFAULT_DEPTH, DEFAULT_L2, DEFAULT_GROW_POLICY,
    GROW_POLICIES, DEFAULT_MIN_DATA_IN_LEAF, validate_config,
)
from src.hardware import verify_gpu


def build_parser():
    ap = argparse.ArgumentParser()
    ap.add_argument('--train', required=True)
    ap.add_argument('--predict', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--seed', type=int, default=20261004)
    ap.add_argument('--threads', type=int, default=8)
    ap.add_argument('--budget', type=float, default=60)
    ap.add_argument('--model-out', default=None)
    ap.add_argument('--feature-mode', choices=FEATURE_MODES, default=FEATURE_MODE)
    ap.add_argument('--iterations', type=int, default=DEFAULT_ITERATIONS)
    ap.add_argument('--depth', type=int, default=DEFAULT_DEPTH)
    ap.add_argument('--l2-leaf-reg', type=float, default=DEFAULT_L2)
    ap.add_argument('--grow-policy', choices=GROW_POLICIES, default=DEFAULT_GROW_POLICY)
    ap.add_argument('--min-data-in-leaf', type=int, default=DEFAULT_MIN_DATA_IN_LEAF)
    return ap


def build_model(args):
    """One fixed learner family; no budget-dependent settings or early stopping."""
    # Never pass an unsupported leaf-support parameter to SymmetricTree.
    support = ({'min_data_in_leaf': args.min_data_in_leaf}
               if args.grow_policy == 'Depthwise' else {})
    return CatBoostClassifier(
        iterations=args.iterations, depth=args.depth, learning_rate=0.08,
        l2_leaf_reg=args.l2_leaf_reg, grow_policy=args.grow_policy,
        loss_function='Logloss', random_seed=args.seed,
        task_type='GPU', devices='0', thread_count=args.threads,
        boosting_type='Plain', one_hot_max_size=10, gpu_ram_part=0.85,
        allow_writing_files=False, verbose=100, **support)


def main():
    args = build_parser().parse_args()
    validate_config(args)
    start = time.monotonic()
    gpu = verify_gpu()
    train = pd.read_csv(args.train)
    predict = pd.read_csv(args.predict)
    if TARGET in predict.columns:
        raise ValueError('Prediction input must not contain target')
    if set(train[TARGET].unique()) != {0, 1}:
        raise ValueError('Training target must be mapped to 0/1')
    X = make_features(train, args.feature_mode)
    Xp = make_features(predict, args.feature_mode)
    if X.columns.tolist() != Xp.columns.tolist():
        raise ValueError('Feature schema mismatch')
    train_pool = Pool(X, label=train[TARGET], cat_features=CATEGORICAL)
    pred_pool = Pool(Xp, cat_features=CATEGORICAL)
    model = build_model(args)
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
    model.save_model(str(artifact), format='cbm')
    alias = copy_compatibility_alias(artifact)
    metadata = {'gpu': gpu, 'fit_elapsed_s': fit_seconds,
                'candidate_elapsed_s': time.monotonic() - start,
                'iterations': model.tree_count_, 'requested_iterations': args.iterations,
                'requested_depth': args.depth, 'requested_l2_leaf_reg': args.l2_leaf_reg,
                'requested_learning_rate': 0.08,
                'requested_grow_policy': args.grow_policy,
                'requested_min_data_in_leaf': (args.min_data_in_leaf
                                               if args.grow_policy == 'Depthwise' else None),
                'tree_leaf_counts': model.get_tree_leaf_counts().tolist(),
                'effective_model_params': model.get_all_params(),
                'model_bytes': artifact.stat().st_size,
                'seed': args.seed,
                'train_n': len(train), 'predict_n': len(predict),
                'feature_mode': args.feature_mode, 'feature_names': X.columns.tolist(),
                'model_params': model.get_params(),
                'compatibility_alias': str(alias), 'compatibility_alias_format': 'cbm'}
    artifact.with_suffix('.metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(json.dumps(metadata), flush=True)


if __name__ == '__main__':
    main()
