# Progress n004: Parallel melon (or melon+carrot) loop

## Plan
Hypothesis: switch (or mix) the n002 parallel hired-hand farm from CARROT to MELON.
Melon seed 80, base 250, harvest at age 10 with daily watering for up to 6 yield.
Same TARGET_HANDS=6 + tile partition. Risk: melon glut crashes price to $1.

## Steps
1. Measure untouched parent (carrot parallel) quick baseline.
2. Implement melon primary loop; harvest at age 10 after water.
3. Iterate quick; try mix / sell timing if glut kills price.
4. Final validation once; write HANDOFF + proposals.json.

## Log
### 2026-09-10 — start
Reading docs + parent agent (CROP=CARROT, TARGET_HANDS=6). Melon notes from RULES:
- seed 80, base 250; bonus window ages 6–12; yield caps at 6 by age 10 with daily water.
- Price: above_func sq, above_target 3.60 → modest oversupply floors at $1.
- constants.py lists max_yield_day=12; will harvest at age 10 per hypothesis/RULES.

### Untouched quick baseline
`eval/eval.py --seedset quick` → score=11690.2 margin=8402.2 win_rate=1.00 errors=0 std=3050.9
(matches parent n002 worker quick).

### Price analysis
Melon has essentially no shop demand (town center eats 1/day). Selling from I0:
~100 units avg $217; ~150 avg $176; floor at ~158 units.
Full 25-tile wave ≈150 units — still profitable once; second wave sells at $1.
Plan: melon primary, harvest age 10; switch plantings to carrot when melon price is crashed.

### Implementing
Melon loop + price-gated carrot fallback; sell both shed crops; buy seeds for active plant crop.

### Melon+carrot-fallback quick
`eval/eval.py --seedset quick` → score=29058.0 margin=25479.7 win_rate=1.00 errors=0 std=436.2
Huge lift vs carrot baseline 11690. Commit this, then ablate: pure melon, mix tiles, price thresholds.

### Price-threshold ablations (quick)
- pure melon (thresh 0): 26606 — second wave loses money at $1
- thresh 80/40/100: 29058
- thresh 120: 31476
- thresh 150/160: 32309
- thresh 180/200/220: 35045 (best uncapped)

### Mid-day DROP haul (thresh 180)
- haul at inv>=6: 34588 — worse than no-haul 35045 (steals field turns). Reverted.

### Melon tile-cap mix (thresh 180, quick)
- uncapped: ~34719–35045
- max 10: 34038; 12: 35480; 14: 36683; **16: 37637**; 18: 33103; 20: 32272
- Grid best: tiles=16 × thresh=180 → 37637.3

### Locked config
MELON_MAX_TILES=16, MELON_PLANT_MIN_PRICE=180, harvest age 10, TARGET_HANDS=6, opportunistic DROP only.
Confirmed quick: 37637.3. Running validation next.

### Validation (final)
`eval/eval.py --seedset validation` → score=36891.8 margin=33510.3 win_rate=1.00 errors=0 std=2092.9 n_games=32
Commit `e6efa200fc49d76d122e3fca4222b3d591b757d5`.
Parent validation was 9084.6 → large improvement. Wrote HANDOFF.md + proposals.json.

