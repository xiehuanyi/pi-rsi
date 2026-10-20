# Handoff n002: Cheap daily hired hands for parallel farm ops
## Hypothesis
Keep a simple carrot crop loop but unlock action bandwidth by hiring several farm hands each day (fib costs are tiny vs crop revenue), partitioning unlocked tiles by board-index mod n_units, and pathing each unit to its nearest pending PLANT/WATER/HARVEST/DIG task so multiple tile-actions happen per turn.

## What I did
- Replaced solo carrot starter with a multi-unit carrot farm in `agent.py`, `src/farm_ops.py`, `src/market.py`, `src/pathing.py`.
- Each day: sell shed carrots, submit `TARGET_HANDS=6` HIRE orders, buy seeds for empty tiles.
- Farmer + hands partition unlocked tiles (`index % n_units`), path greedily, prioritize WATER then HARVEST (water on max-yield day before harvest for full carrot bonus).
- Tuned away mid-day shed hauls (EOD drop + morning sell); tried other hand counts and seed-buy policies.

## Result
- Baseline quick: score 3491.3 (untouched starter).
- Best quick: score 11690.2 (margin 8402.2, win_rate 1.00, errors 0, std 3050.9) — `eval/eval.py --seedset quick`.
- Validation: score 9084.6 (margin 5888.0, win_rate 1.00, errors 0, std 1877.2, n_games 32) — `eval/eval.py --seedset validation`.
- Final git commit: `d48c7758ed950bd36d792aed1fa3435c81316e17`.

## Mechanism
Hiring cheap daily hands multiplies tile-actions per day, so the agent fills all 25 NW tiles instead of farming one carrot under the farmer. That alone lifts mean money ~2.5–3× vs the solo starter. Watering before harvest on the max-yield day captures the last carrot bonus unit (yield 3 vs 2). Keeping units in the field (no mid-day DROP marches) preserves harvest/replant bandwidth. Hire costs (~20/day for 6 hands) are negligible. Large remaining gap to ~138k comes from still using only carrots on NW land with no animals, fertilizer, land buys, or demand-timed selling.

## Dead ends
- TARGET_HANDS=8: quick 8297 — more hands scatter ownership and burn capital on seeds without finishing cycles better.
- TARGET_HANDS=5: quick 8328 — under-bandwidth vs 6.
- Aggressive full-field seed stockpiling: quick 9118 — ties up money that should stay liquid for nothing useful.
- Mid-day DROP pathing to shed (threshold 6): quick 10751, worse than opportunistic-only DROP at 11690 — hauls steal harvest turns.
- Harvest-before-final-water (first commit): quick 8877 — misses +1 yield/plant.

## Next hypotheses
1. Buy NE land (~$1k) once carrot cashflow is stable and extend the same hand-partitioned plant loop onto 50 tiles — doubles plantable area with the same hire machinery.
2. Switch the parallel loop from carrot to melon (or mix): higher base price; hands make the longer grow cycle workable via parallel watering.
3. Add fertilizer pickup/use on one-time crops during the bonus window (hands collect from a few geese or BUY_PRODUCT) to push carrot/melon to max yield.

## Open questions
- Is board-index modulo the best partition once NE unlocks (tiles become non-contiguous for a unit)?
- Should harvest day intentionally leave some tiles empty to desynchronize cohorts for steadier daily cash?
- How much of validation variance is town-shop carrot demand vs agent policy?
