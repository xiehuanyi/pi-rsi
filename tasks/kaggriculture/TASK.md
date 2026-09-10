# Task: Kaggriculture agent

Kaggriculture is a two-player farming simulation from a Kaggle competition (`kaggle-environments` 1.32.7, environment
`kaggriculture`). Two farms share one market for 30 days × 24 turns = 720 turns. Each turn the farmer (plus any hired
hands) takes one action (move, plant, water, harvest, feed, build, ...) and the player may submit up to 10 market orders
(buy seeds/animals, sell produce, hire hands, buy land). The winner is the player with more money at the end.

## Goal
Maximize the agent's **mean final money** when playing against the built-in `starter` opponent (a single carrot loop),
averaged over fixed seeds and both seats. This is the competition reward (final bank balance), measured locally.

## Deliverable
A deterministic Python agent: `agent.py` exposing `agent(obs) -> action` with helpers in `src/`, runnable by the frozen
evaluator without network access, and fast enough to respect the per-action time limit (1 s per action with a 60 s
overage budget per game).

## Metric
`score` = mean final money of the agent over the seed set (higher is better), reported by `eval/eval.py`.
Seed sets: `quick` (6 seeds × 2 seats, for iteration), `validation` (16 × 2, the official node score computed by the
harness), `test` (32 × 2, held out for the final report). A game where the agent raises an exception or times out
scores 0, so robustness matters as much as strategy.

## Known reference points (same evaluator, same opponent)
- Starter agent (this baseline): about 3,500.
- A strong hand-engineered agent from the competition (multi-crop economy, hired hands, animals, market timing):
  about 138,000 on the validation seed set. The headroom is large; early gains come from using more of the farm, more of the day, and
  higher-value crops with correct watering; later gains come from hands, land, animals, and selling into demand
  instead of into gluts.

## Constraints
- Do not modify `eval/` or `docs/`.
- Keep the agent deterministic and side-effect free (no files, no network, no background threads).
- Keep `agent.py` as the entry point; put logic in `src/` modules, each under 400 lines.
