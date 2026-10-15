#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
# Existing cache only: no downloads, datasets, or global environment changes.
export UV_OFFLINE=1
export OMP_NUM_THREADS=8 OPENBLAS_NUM_THREADS=8 MKL_NUM_THREADS=8 NUMEXPR_NUM_THREADS=8
if [[ ! -x .venv/bin/python ]]; then
  uv venv --python 3.12 .venv
fi
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python prepare.py
