# Handoff n004: Parallel melon (or melon+carrot) loop
## Hypothesis
Replace or mix the n002 parallel hired-hand carrot farm with MELON (seed 80, base 250, harvest at age 10 after daily watering for up to 6 yield). Same TARGET_HANDS=6 and tile-index partition; keep a carrot subset when melon glut crashes price. Expected large gain if price holds; risk that above_target oversupply floors melon at $1.

## What I did
- Switched primary crop to MELON with `HARVEST_AGE["MELON"]=10` (water-before-harvest) in `src/farm_ops.py`; kept tending both MELON and CARROT plants.
- `choose_plant_crop` / `build_market_orders` (`agent.py`, `src/market.py`): plant and buy melon seeds only while `prices["MELON"] >= 180` and live melon tiles `< 16`; otherwise plant/buy carrot. Sell both shed crops.
- Tuned on quick: price gate, tile cap, rejected mid-day DROP hauls.
- Final knobs: `MELON_MAX_TILES=16`, `MELON_PLANT_MIN_PRICE=180`, `TARGET_HANDS=6`, opportunistic shed-adjacent DROP only.

## Result
- Untouched parent quick: score 11690.2 (`eval/eval.py --seedset quick`).
- Best worker quick: score 37637.3 (margin 34208.8, win_rate 1.00, errors 0, std 1450.4) — `eval/eval.py --seedset quick`.
- Validation: score 36891.8 (margin 33510.3, win_rate 1.00, errors 0, std 2092.9, n_games 32) — `eval/eval.py --seedset validation`.
- Parent validation was 9084.6; lift ≈ +27.8k mean money.
- Final git commit: `e6efa200fc49d76d122e3fca4222b3d591b757d5`.

## Mechanism
Melon’s base $250 and yield 6 make one watered 10-day cycle worth far more per tile than carrot, and hands make the long water schedule workable across many tiles. Melon has almost no town-shop demand (center eats 1/day), so selling a full 25-tile wave (~150 units) rides the sq/above_target=3.60 curve into the $1 floor and a second melon wave loses money. Capping at 16 live melon tiles (~96 units) keeps average sale price higher and frees 9 tiles for carrots that earn during the grow and after the glut. Gating replants on price ≥ 180 stops seeding melon into a crashed market. Hire costs stay negligible vs crop revenue.

## Dead ends
- Pure melon forever (price gate 0): quick 26606 — second wave sells near $1 and burns seed capital.
- Price gate 80 (first commit): quick 29058 — still replants too much melon before switching.
- Mid-day DROP haul at inv≥6 (thresh 180): quick 34588 vs no-haul 35045 — hauls steal harvest/replant turns.
- Melon tile caps 10 / 18 / 20: quick 34038 / 33103 / 32272 — worse than 16.
- tiles=16 × thresh=200: quick 32056 — switches off melon too aggressively.

## Next hypotheses
1. Buy NE land (~$1k) once melon+carrot cashflow is stable and extend the hand-partitioned mix onto ~50 tiles, keeping a melon tile cap scaled to the price curve (~16–20 total melons, not double).
2. Add fertilizer (BUY_PRODUCT or goose collect) on melon during bonus window ages 6–8 to hit yield 6 by age 8 and free two days per cycle for an extra harvest before season end.
3. Demand-timed / drip selling: sell melon in small lots across turns (and hold near I0) while carrots fund ops; may raise realized melon $/unit vs dumping a full shed order.

## Open questions
- Is 16 the validation-optimal melon cap, or does validation’s shop draw want a different cap than quick?
- Does buying NE with the same 16-melon cap beat staying on NW, or does extra carrot land dominate?
- How much shed overflow (cap 100) still discards melon when inventories EOD-dump after a synchronized harvest?
