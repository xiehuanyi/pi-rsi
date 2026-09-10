# Task: toy long-running job (harness test task)

A synthetic regression problem (20 inputs, one noisy nonlinear target) trained by a small MLP under a fixed
wall-clock budget. The point of this task is the machinery: jobs run through the queue, emit a learning curve, can be
early-stopped against the incumbent, can be killed for stalling, and can resume from a checkpoint.

## Goal
Minimize validation RMSE reachable within the budget (`smoke` 4 s for iteration, `proxy` 12 s official, `full` 20 s
for the final ranking of the top nodes). Lower is better.

## Deliverable
`src/trainer.py` exposing `train(budget_s, run_dir, resume, data, report)` (see docs/CONTRACT.md) plus `config.toml`.
The frozen wrapper `eval/run.py` generates the data, calls your trainer, scores every reported epoch on the validation
set, and scores the returned test predictions at the end.

## Constraints
- Do not edit `eval/` or `docs/`. CPU only, numpy only. Respect the budget: the wrapper kills runs that overrun.
- Checkpoint into `run_dir` and honour `resume=True` so a restarted job continues instead of starting over.
