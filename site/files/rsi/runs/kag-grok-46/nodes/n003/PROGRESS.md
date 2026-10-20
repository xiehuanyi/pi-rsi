# n003 progress

Hypothesis: Buy NE land (then SW) once money exceeds ~4000, raise MAX_HANDS to 7–8, plant the new 25 tiles with the same wheat stay-on-tile loop.

## Plan
1. Measure untouched parent (n002 wheat+hire) on quick seed set.
2. Implement BUY_LAND NE then SW, MAX_HANDS 7–8, expand plant budget to unlocked tiles.
3. Iterate on quick, then run validation.

## 2026-09-10 start
Reading parent policy (`src/policy.py`, `src/constants.py`, `src/grid.py`) and docs for BUY_LAND. BUY_LAND takes no quadrant arg; costs are $1k / $2k / $4k for NE / SW / SE in order. Hands spawn first on (5,4) which is locked until NE is bought.

About to run untouched quick baseline.

## Untouched baseline
- quick: score 15888.3 (12 games, errors=0, std=715.4, margin=12293.5, win_rate=1.00). Command: `eval/eval.py --seedset quick`
- Matches n002 parent (15888.33).

## Implementation sketch
- BUY_LAND after SELL when cash exceeds ~4000 (NE $1000) then ~6500 (SW $2000); keep post-purchase reserve for seeds/hires.
- MAX_HANDS 7 (fib 1+1+2+3+5+8+13=$33). Plant every unlocked tile (25→50→75).
- Do not buy SE. Do not buy land after the last wheat plant day (25).
- Reuse stay-on-tile greedy. Hands spawning on (5,4) become useful once NE unlocks.
- Shed cap 100 vs ~200 wheat/cycle if harvests sync: DROP when a unit carries >=12 so SELL can clear the shed mid-day. NE is planted a day after first harvest so the two fields stagger.

## 2026-09-10 code v1
Changed `src/constants.py` (MAX_HANDS=7, land thresholds, DROP_INVENTORY_THRESHOLD=12), `src/policy.py` (BUY_LAND after SELL, plant all unlocked tiles, mid-day DROP), `agent.py` docstring.

### quick v1
- quick: score 19436.0 (was 15888.3); margin 15853.2; win_rate 1.00; errors 0; std 188.7. Command: `eval/eval.py --seedset quick`
- seed 101 seat 0: 19491, unlocked NW+NE+SW. NE bought day 5 after first SELL. SW bought day 12.
- Problems: harvest days leave 6–11 unwatered; weeds 3–5; DROP_THRESHOLD=12 sent actors back to the shed mid-harvest; SW added ~8 tended tiles for $2000 and more weeds. Final plants ~56/75.

## 2026-09-10 v2 (seed-101 ablations, seat 0)
- NE-only MAX_HANDS=8 DROP=24: 22454
- NE+SW@6500 hands=8: 21539
- NE+SW@6500 hands=7: 20475
- NE+SW@9000 hands=8: 21222
- SW hands=9/10/12: 21841 / 21227 / 21227 — all worse than NE-only
- NE-only hands=6/7/8 mean over seeds 101-103: 19977 / 21521 / 22294
- NE min 3500 vs 4000 vs 4500: identical (first-harvest SELL always clears 4000)
- HIRE_CASH_RESERVE 300 vs 600: identical

SW is a dead end at 7–12 hands: $2000 leaves the bank and 75 tiles exceed labor, causing missed water and weeds. Shipping NE-only, MAX_HANDS=8, DROP only when idle / hour>=21 / carried>=24.

### quick v2
- quick: score 22343.1 (was 15888.3); margin 18789.3; win_rate 1.00; errors 0; std 179.2; min 21939 max 22483. Command: `eval/eval.py --seedset quick`
- Reordering market to BUY_SEED before HIRE scored 22252.2 (slightly worse; land-buy morning then only 7 hires). Reverted to HIRE-then-SEED.

### validation v2
- validation: score 22269.0 (was 16216.75 at n002); margin 18708.3; win_rate 1.00; errors 0; std 235.6; min 21767 max 22483; n_games 32. Command: `eval/eval.py --seedset validation`
- git: `c23113bcc9578e6c35693e7c52ea007312cef2f5`

NE doubled the field after day 5 and 8 hands kept watering-only days clean. SW is a dead end at this labor level. Next lever is fertilizer (4→6 wheat yield) now that 50 tiles are online; that will also force mid-day DROP because 50×6 exceeds the shed cap of 100.
