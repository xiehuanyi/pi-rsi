# Kaggriculture agent workspace

- `agent.py` — entry point; must keep a module-level callable `agent(obs) -> action_dict`.
- `src/` — helpers (this directory is on `sys.path` when the evaluator loads `agent.py`).
- `eval/` — frozen evaluator and seed sets. Do not edit. Run it, do not change it.
- `docs/` — official rules (`RULES.md`), getting-started guide with observation/action formats (`GETTING_STARTED.md`),
  and the environment specification (`kaggriculture.spec.json`). Do not edit.

Evaluate: `<python> eval/eval.py --seedset quick` (6 seeds × 2 seats, ~10 s) or `--seedset validation` (16 seeds × 2 seats).
The score is the agent's mean final money against the built-in `starter` opponent. `metrics.<seedset>.json` holds
per-game details (`per_seed`), including any agent errors (an erroring agent scores 0 for that game).
