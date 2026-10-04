#!/usr/bin/env python3
"""Frozen ROC-AUC evaluator. Labels never enter candidate CLI or returned metrics."""
from __future__ import annotations
import os
for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
    os.environ[key] = '8'
import argparse
import hashlib
import json
import signal
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from hardware import verify_gpu

ROOT = Path(__file__).resolve().parent.parent
BUDGETS = {'quick': 60, 'validation': 180, 'final': 240}
MODEL_SEED = 20261004
TARGET = 'satisfaction'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def protocol_hash():
    files = ['eval.py', 'hardware.py', 'run.py', 'data_manifest.json']
    value = {p: sha(Path(__file__).parent / p) for p in files}
    value['budgets'] = BUDGETS
    value['seed'] = MODEL_SEED
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    tmp.replace(path)


def checked_file(path, key, manifest):
    expected = manifest['files'][key]['sha256']
    actual = sha(path)
    if actual != expected:
        raise ValueError(f'Frozen data hash mismatch: {key}')
    return actual


def limited_cpu():
    if hasattr(os, 'sched_getaffinity'):
        cpus = sorted(os.sched_getaffinity(0))[:8]
        os.sched_setaffinity(0, cpus)


def evaluate(agent_dir, level, out, python, quiet=False):
    start = time.monotonic()
    agent = Path(agent_dir).resolve()
    out = Path(out).resolve()
    work = out.parent
    work.mkdir(parents=True, exist_ok=True)
    result = {'score': None, 'level': level, 'uncertainty': 'unknown; GPU CatBoost is not bitwise deterministic'}
    stage = None
    try:
        if level not in BUDGETS:
            raise ValueError(f'Unknown level: {level}')
        if level == 'final':
            # Explicitly changing the campaign config is required. Default task pack is sealed.
            with (ROOT / 'task.toml').open('rb') as f:
                cfg = tomllib.load(f)
            if cfg['eval'].get('final_seedset') != 'final':
                raise RuntimeError('Final holdout sealed: enable only explicitly at the end of the entire campaign')
        result['protocol_sha256'] = protocol_hash()
        manifest = json.loads((Path(__file__).parent / 'data_manifest.json').read_text())
        result['manifest_sha256'] = sha(Path(__file__).parent / 'data_manifest.json')
        result['budget_s'] = BUDGETS[level]
        result['model_seed'] = MODEL_SEED
        result['gpu'] = verify_gpu()
        if not (agent / 'train.py').is_file():
            raise FileNotFoundError('Candidate must provide train.py')
        result['candidate_entry_sha256'] = sha(agent / 'train.py')
        if level == 'quick':
            train_path = agent / 'data/quick_train.csv'
            dev_path = agent / 'data/quick_dev.csv'
            train_hash = checked_file(train_path, 'starter/data/quick_train.csv', manifest)
            label_hash = checked_file(dev_path, 'starter/data/quick_dev.csv', manifest)
            dev = pd.read_csv(dev_path, dtype={'id': 'string'})
            labels = dev[['id', TARGET]].copy()
            features = dev.drop(columns=TARGET)
            stage = tempfile.TemporaryDirectory(prefix='quick-input-', dir=work)
            pred_input = Path(stage.name) / 'features.csv'
            features.to_csv(pred_input, index=False)
            pred_output = work / 'predictions.csv'
            log = work / 'candidate.log'
        else:
            # Root is always the ORIGINAL frozen task pack under harness job/ordinary modes.
            private = ROOT / 'private'
            train_path = private / 'train_pool.csv'
            pred_input = private / f'{level}_features.csv'
            label_path = private / f'{level}_labels.csv'
            train_hash = checked_file(train_path, 'private/train_pool.csv', manifest)
            checked_file(pred_input, f'private/{level}_features.csv', manifest)
            label_hash = checked_file(label_path, f'private/{level}_labels.csv', manifest)
            labels = pd.read_csv(label_path, dtype={'id': 'string'})
            features = pd.read_csv(pred_input, dtype={'id': 'string'})
            # Keep official predictions/logs out of candidate worktrees and public metrics.
            store = private / 'evaluations'
            store.mkdir(exist_ok=True)
            private_run = Path(tempfile.mkdtemp(prefix=level + '-', dir=store))
            pred_output = private_run / 'predictions.csv'
            log = private_run / 'candidate.log'
        if TARGET in features.columns or features.columns.tolist() != manifest['columns'][:-1]:
            raise ValueError('Prediction feature schema invalid or contains labels')
        if labels.columns.tolist() != ['id', TARGET] or not labels['id'].equals(features['id']):
            raise ValueError('Frozen feature/label IDs do not align')
        if labels['id'].isna().any() or not labels['id'].is_unique:
            raise ValueError('Invalid held-out IDs')
        if labels[TARGET].isna().any() or set(labels[TARGET].unique()) != {0, 1}:
            raise ValueError('Holdout must contain both mapped classes 0 and 1')
        result.update({'n': len(labels), 'train_n': manifest['files'][
            'starter/data/quick_train.csv' if level == 'quick' else 'private/train_pool.csv']['rows'],
            'data_sha256': {'train': train_hash, 'prediction_features': sha(pred_input), 'labels': label_hash}})
        model_path = work / 'model.cbm'
        metadata_path = model_path.with_suffix('.metadata.json')
        # Never accept a stale prediction or model from an earlier run.
        for p in (pred_output, model_path, metadata_path):
            p.unlink(missing_ok=True)
        # Do not resolve the venv interpreter symlink to the system Python.
        interpreter = str(Path(python).absolute()) if Path(python).exists() else python
        cmd = [interpreter, str(agent / 'train.py'), '--train', str(train_path),
               '--predict', str(pred_input), '--out', str(pred_output),
               '--seed', str(MODEL_SEED), '--threads', '8', '--budget', str(BUDGETS[level]),
               '--model-out', str(model_path)]
        env = os.environ.copy()  # CUDA visibility preserved exactly; never expanded.
        candidate_start = time.monotonic()
        with log.open('w') as lf:
            process = subprocess.Popen(cmd, cwd=agent, env=env, stdout=lf,
                                       stderr=subprocess.STDOUT, start_new_session=True,
                                       preexec_fn=limited_cpu)
            try:
                code = process.wait(timeout=BUDGETS[level])
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=10)
                raise TimeoutError(f'Candidate exceeded {BUDGETS[level]}s training/prediction cap')
            finally:
                # Reap descendants even if a candidate launches work then exits early.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                result['candidate_elapsed_s'] = time.monotonic() - candidate_start
        if code != 0:
            raise RuntimeError(f'Candidate exited {code}; inspect {log}')
        predictions = pd.read_csv(pred_output, dtype={'id': 'string'})
        if predictions.columns.tolist() != ['id', TARGET]:
            raise ValueError('Prediction CSV must contain exactly id,satisfaction')
        if len(predictions) != len(labels):
            raise ValueError('Prediction row count mismatch')
        if not predictions['id'].is_unique or not predictions['id'].equals(labels['id']):
            raise ValueError('Prediction IDs/order mismatch')
        prob = pd.to_numeric(predictions[TARGET], errors='raise').to_numpy(dtype=float)
        if not np.isfinite(prob).all() or not ((prob >= 0) & (prob <= 1)).all():
            raise ValueError('Probabilities must be finite and in [0,1]')
        result['score'] = float(roc_auc_score(labels[TARGET].to_numpy(), prob))
        result['prediction_sha256'] = sha(pred_output)
        if model_path.is_file():
            result['model_sha256'] = sha(model_path)
        if metadata_path.is_file():
            # Diagnostic only: score/timing/hardware authority is the evaluator.
            result['candidate_report'] = json.loads(metadata_path.read_text())
        result['elapsed_s'] = time.monotonic() - start
        atomic_json(out, result)
        if not quiet:
            print(json.dumps(result, allow_nan=False))
        return 0
    except Exception as exc:
        result.update({'score': None, 'error': f'{type(exc).__name__}: {exc}',
                       'elapsed_s': time.monotonic() - start})
        # Ignore malformed untrusted candidate metadata when recording failure.
        result.pop('candidate_report', None)
        atomic_json(out, result)
        if not quiet:
            print(json.dumps(result), file=sys.stderr)
        return 1
    finally:
        if stage is not None:
            stage.cleanup()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--agent-dir', default='.')
    ap.add_argument('--seedset', choices=list(BUDGETS), default='quick')
    ap.add_argument('--out', default=None)
    ap.add_argument('--python', default=sys.executable)
    ap.add_argument('--quiet', action='store_true')
    args = ap.parse_args()
    out = args.out or str(Path(args.agent_dir) / 'runs' / args.seedset / 'metrics.json')
    return evaluate(args.agent_dir, args.seedset, out, args.python, args.quiet)


if __name__ == '__main__':
    sys.exit(main())
