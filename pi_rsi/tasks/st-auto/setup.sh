#!/usr/bin/env bash
# Creates the task's private virtualenv (tabular ML stack) and prepares the data split.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
uv venv --python 3.12 .venv >/dev/null
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python prepare.py
