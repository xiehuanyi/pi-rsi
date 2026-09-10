#!/usr/bin/env bash
# Creates the task's private virtualenv (tabular ML stack) and prepares the data split.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
if command -v uv >/dev/null 2>&1; then
  uv venv --python 3.12 .venv >/dev/null
  uv pip install --python .venv/bin/python -r requirements.txt
else
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi
.venv/bin/python prepare.py
