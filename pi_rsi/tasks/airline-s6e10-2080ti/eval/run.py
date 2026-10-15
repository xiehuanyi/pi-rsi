#!/usr/bin/env python3
"""Harness GPU-job adapter; all scoring is delegated to the frozen evaluator."""
import argparse
import sys
from pathlib import Path
from eval import BUDGETS, atomic_json, evaluate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--budget', required=True, type=float)
    ap.add_argument('--run-dir', required=True)
    args = ap.parse_args()
    out = Path(args.run_dir).resolve() / 'metrics.json'
    levels = {float(v): k for k, v in BUDGETS.items()}
    if args.budget not in levels:
        atomic_json(out, {'score': None, 'error': f'Unknown job budget: {args.budget}'})
        return 1
    return evaluate(Path.cwd(), levels[args.budget], out, sys.executable, quiet=False)


if __name__ == '__main__':
    sys.exit(main())
