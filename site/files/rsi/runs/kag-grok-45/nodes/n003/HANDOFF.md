# Handoff n003: Buy NE land, extend hand farm
## Hypothesis
Once money exceeds ~4000, submit BUY_LAND for NE ($1000). Keep TARGET_HANDS=6–8 and the same index-mod partition / pathing / carrot water-before-harvest loop, but operate on all unlocked tiles (50 instead of 25). Double plantable area should roughly double crop revenue with the same hire economics.

## What I did
- Added `BUY_LAND` in `src/market.py` (`build_market_orders`) when liquid money > `LAND_BUY_MONEY_THRESHOLD` (4000) and NE is not yet unlocked; cost tracked via `LAND_COSTS` / env order NE→SW→SE.
- Exposed `LAND_BUY_MONEY_THRESHOLD` in `src/farm_ops.py`; farm loop already used `unlocked_tiles`, so NE auto-entered the plant/water/harvest set.
- Updated `agent.py` docstring for n003.
- Tuned within-hypothesis: TARGET_HANDS 6–12, thresholds 4k–12k, contiguous-block and quadrant-local partitions, plant-tile caps 25–50. None beat the no-land baseline.
- Final shipped code restores the hypothesized recipe: BUY_LAND @ >4000, TARGET_HANDS=6, original index-mod partition.

## Result
- Baseline quick (untouched n002): score 11690.2 (`eval/eval.py --seedset quick`).
- Final quick: score 8656.7 (margin 5440.7, win_rate 1.00, errors 0, std 962.1) — worse than baseline.
- Final validation: score 8229.4 (margin 5024.2, win_rate 1.00, errors 0, std 2640.0, n_games 32) — worse than parent n002 validation 9084.6.
- Best quick among land variants (not shipped): plant-cap 32 + contiguous ≈ 9221 — still below no-land.
- Final git commit: `97ceabeca6a9d6aa457307e8141fdb1cf00704cb`.

## Mechanism
Doubling carrot acreage does not double money because carrot pricing is calibrated with T≈450 for one 5×5 field. Flooding a second field of carrots pushes market inventory well above I0 and crashes price (seed-0 trace: ~$21 with NW-only vs ~$5 with NW+NE by day 29). Extra volume is sold into a glut, so revenue falls even when plants grow. Secondary issues (index-mod travel across NW/NE, watering misses, more hands fragmenting work) also hurt, but price collapse alone explains why “2× tiles ⇒ 2× money” fails for same-crop expansion.

## Dead ends
- TARGET_HANDS=8/10 with land @4000: quick 6668 / 4055 (mod) and 7120 / worse with contiguous — more hands hurt, matching n002.
- Delaying land (thresh 7k–12k, hands=6): quick 10652–11232 — approaches no-land but never beats it.
- Contiguous-block partition: quick 9015 — helps locality slightly, not enough.
- Quadrant-split ownership: quick 8714 — no win.
- Dynamic hands 6→8/10/12 after NE: quick 7115 / 4739 / 3665 — worse.
- Plant caps 25–50: best 9221 at cap=32 — still below baseline; fallow NE ranks steal unit ownership if partition spans all unlocked tiles.

## Next hypotheses
1. Buy NE but put a different product on it (melon or animals/eggs), keep carrots on NW — diversify into unsaturated markets instead of 2× carrots.
2. Stay on NW (no land buy) and switch the parallel hand loop from carrot to melon for higher base price without glutting the carrot curve.
3. Price-aware selling / production throttle on carrots (hold in shed, sell only above a price floor) before any acreage expansion.

## Open questions
- How much NE melon (or goose eggs) can 6–8 hands support without starving the NW carrot water cycle?
- Does modest NE carrot acreage (e.g. +5–8 tiles) ever help if sells are throttled, or is any extra carrot supply dominated by the sqrt glut curve?
- Is BUY_LAND ever correct before the agent has a second product line ready?
