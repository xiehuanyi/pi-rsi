# Progress n006: Fertilize melons for age-8 max yield

## Plan
- Measure untouched parent (n004) quick baseline.
- Buy FERTILIZER via BUY_PRODUCT, PICKUP, FERTILIZE melons in bonus window (ages 6–8).
- Harvest fertilized melons at age 8 (cap 6) instead of 10; keep unfertilized at 10.
- Tune buy quantity / when to fertilize vs water/harvest bandwidth.

## Runs

## Baseline
- Untouched parent quick: score=37637.3 (margin=34208.8, win_rate=1.00, errors=0, std=1450.4) via `eval/eval.py --seedset quick`.

## Mechanism check (env unit test)
- Melon `first_yield_day=10`, `max_yield_day=12`, max_yield=6.
- With FERTILIZE on age 5 then daily water: yield hits 6 at age 8, but HARVEST is a no-op until age 10 (env gate).
- Without fertilizer: yield hits 6 at age 10; harvest succeeds at 10.
- Conclusion: fertilize cannot shorten melon cycle; hypothesis's "harvest at 8 / third wave" is mechanically blocked. Still implementing as stated to measure cost of fert+failed early harvest / fert-only.


## Attempt 1: BUY_PRODUCT fert + FERTILIZE age-5 melons; harvest clamped to first_yield_day=10
- Expect: no cycle speedup; fert cost (~100/melon) and pickup/fert actions steal bandwidth → score drop vs 37637.
- Result quick: score=33820.5 (margin=30461.6, win_rate=1.00, errors=0, std=1555.2) — down ~3.8k vs baseline 37637. Fertilizer spend + pickup/fert actions hurt with no cycle gain.

## Attempt 2: same fert but HARVEST at age 8 without first_yield clamp (hypothesis literal)
- Expect: worse — ages 8–9 HARVEST no-ops waste field bandwidth.
- Result quick: score=6975.0 (margin=3464.2, win_rate=1.00, errors=0, std=944.5) — catastrophic; HARVEST no-ops at ages 8–9 starve watering/replant.

## Decision
- Hypothesis mechanically impossible for cycle shortening; fert-only costs money/actions.
- Revert agent to parent n004 melon loop (no fertilizer) as final code.
- Next: run validation on reverted parent code.

## Final (reverted parent)
- quick: score=37637.3 (margin=34208.8, win_rate=1.00, errors=0, std=1450.4)
- validation: score=36891.8 (margin=33510.3, win_rate=1.00, errors=0, std=2092.9, n_games=32)
- commit: d53f99ba66ac3b13ff0b29fba5aa100a34b73d7e
- Hypothesis REFUTED: melon first_yield_day=10 blocks early harvest; fertilizer cannot unlock a third wave.
- Wrote HANDOFF.md and proposals.json.
