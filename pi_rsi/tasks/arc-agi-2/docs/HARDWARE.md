# Hardware and environment

- GPU: one NVIDIA RTX 3090 (24 GB). About 7 GB is permanently used by another process, so plan for ~15 GB.
  `CUDA_VISIBLE_DEVICES` is set by the job queue; always use device 0 (`.cuda()`).
- CPU: 52 cores, 250 GB RAM. Disk is plentiful.
- Python env: `.venv/bin/python` with torch 2.8 (cu128), transformers 5.12, peft 0.19, accelerate, numpy. No flash-attention,
  no vLLM, no unsloth, no bitsandbytes. No network: do not pip install or download; everything you need is here.
- Models (offline, under `models/`): `Qwen2.5-0.5B-Instruct` (fast; the starter), `Qwen2.5-1.5B-Instruct`,
  `Qwen3.5-2B` (hybrid attention; loads but runs without fast kernels, expect it to be slow).
- Budgets (wall-clock, enforced by the job queue which kills the job at `job_timeout_s`): smoke 240 s training + up to
  300 s inference on 10 tasks; proxy (official) 1800 s + up to 1500 s inference on 40 tasks; full 7200 s + up to
  4500 s on all 120 tasks. Measured with the starter: 0.5B LoRA training does ~25 optimizer steps/min at
  grad_accum 8; greedy decoding costs ~10 s per query with the starter's batching (2 queries per test input).
