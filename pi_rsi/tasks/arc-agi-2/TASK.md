# Task: ARC-AGI-2 from scratch on one GPU

Build a solver for ARC-AGI-2 (the abstraction-and-reasoning benchmark) that, within a fixed wall-clock budget on one
RTX 3090, produces two candidate output grids for each test input of the public evaluation tasks. The starter
fine-tunes a 0.5B language model on the 1000 public training tasks and decodes greedily; it solves nothing yet.

## Goal
Maximize `score = pass2 + 0.001 * cell_acc` on hidden evaluation outputs (higher is better). `pass2` is the fraction
of tasks whose test inputs are all exactly solved by one of two attempts; it is the metric of the ARC Prize.

## Deliverable
`src/solver.py` exposing `solve(train_tasks, eval_tasks, budget_s, run_dir, resume, report, infer_budget_s)` that
returns `{task_id: [[attempt1, attempt2] per test input]}` with valid grids, plus whatever modules and `config.toml`
you need. It must respect the training budget (`budget_s` seconds), the inference budget, checkpoint into `run_dir`
and continue when `resume` is true, and run offline with the installed packages and the models under `models/`.

## Levels and protocol
- `smoke`: 240 s training + 300 s inference on 10 fixed tasks — your iteration signal (`<python> eval/run.py
  --budget 240 --run-dir runs/smoke`, see `runs/smoke/metrics.json`).
- `proxy` (official node score): 1800 s + 1500 s inference on 40 fixed tasks, run by the harness through the job
  queue after your session ends; you are woken once afterwards to fold the result into your handoff.
- `full`: 7200 s + 4500 s on all 120 tasks for the top nodes at the end.
Jobs are killed at the timeout (no partial credit), stalled jobs (no curve point for 30 min) are killed too: call
`report(step, value)` regularly during training and inference.

## Expectations and references
Fine-tuned small LMs without test-time adaptation score about 0-2% pass@2 on ARC-AGI-2; test-time training and
augmentation voting are what moved ARC-AGI-1 scores for small models and are the obvious first things to try here.
Reference points: the best ARC Prize 2025 Kaggle entries reached roughly 24% on the private ARC-AGI-2 set with far
more compute; frontier reasoning models reach around 30% with very large inference budgets. Any exact match on the
proxy set is progress; report cell accuracy and shape accuracy as diagnostics, not as achievements.

## Constraints
- Do not modify `eval/` or `docs/`; never read `private/` (it is outside your worktree and the harness checks for it).
- Deterministic seeds; keep the solver contract; no network; free GPU memory between phases (`torch.cuda.empty_cache()`).
- One hypothesis per node. Measure with smoke before committing; cite numbers from `runs/*/metrics.json` with the level.
