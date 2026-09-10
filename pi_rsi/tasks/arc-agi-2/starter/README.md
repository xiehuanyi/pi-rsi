# ARC-AGI-2 workspace

- `src/solver.py` — the deliverable; keep `solve(train_tasks, eval_tasks, budget_s, run_dir, resume, report, infer_budget_s)`.
- `src/grids.py` — serialization, parsing, augmentation helpers.
- `config.toml` — starter knobs (model path, sequence limits, LoRA, lr).
- `data/training/` (1000 tasks with outputs), `data/evaluation_inputs/` (120 tasks, test outputs removed).
- `models/` — offline models: `Qwen2.5-0.5B-Instruct`, `Qwen2.5-1.5B-Instruct`, `Qwen3.5-2B` (needs no fast kernels; slower).
- `eval/run.py` — frozen wrapper (do not edit). `eval/subsets.json` — task ids per level.

Smoke run (4 min training + up to 5 min inference on 10 hidden-output tasks):
`<python> eval/run.py --budget 240 --run-dir runs/smoke` → `runs/smoke/metrics.json` (`score`, `pass2`, `cell_acc`, ...).
