#!/usr/bin/env bash
# venv with CUDA torch, the ARC-AGI-2 data split, and small models downloaded for offline use.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"
uv venv --python 3.12 .venv >/dev/null
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python prepare.py
.venv/bin/python -c "
from huggingface_hub import snapshot_download
for m in ['Qwen/Qwen2.5-0.5B-Instruct', 'Qwen/Qwen2.5-1.5B-Instruct']:
    p = snapshot_download(m, local_dir='models/' + m.split('/')[-1], allow_patterns=['*.json','*.safetensors','*.txt','*.jinja','merges.txt','vocab.json'])
    print('downloaded', m, '->', p)
"
.venv/bin/python -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available(), torch.cuda.get_device_name(0))"
