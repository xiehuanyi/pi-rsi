# Progress n008: Quadrant-local hand partition

## Plan
Replace flat `board-index % n_units` ownership with quadrant-aware assignment:
- units 0..2 → NW tiles
- units 3..6 → NE tiles (after unlock)
Keep TARGET_HANDS=6 and MELON_MAX_TILES=16. Emergency WATER/HARVEST cross-quadrant help stays.

## Baseline (untouched parent code)
- quick: score **38707.5** (margin 35273.2, win_rate 1.00, errors 0, std 2494.5)
  `eval/eval.py --seedset quick`

## Implementation
Replace `tile_flat_index % n_units` with quadrant-local ownership:
- Pre-NE: keep flat partition (same as parent).
- Post-NE: units 0..2 → NW, units 3..6 → NE; within-quadrant local index % n_owners.
- Keep emergency WATER/HARVEST/DIG cross-quadrant when a unit has no owned work.
- TARGET_HANDS=6, MELON_MAX_TILES=16 unchanged.

## Eval: first quadrant split (3 NW / 4 NE)
- quick: score **37004.4** (margin 33630.8, win_rate 1.00, errors 0, std 2254.3)
  — **−1703 vs baseline 38707.5**. Regression.

## Eval: emergency-before-PLANT (still 3/4)
- quick: **33989.0** — worse; NE units abandon planting to chase NW water.

## Eval: 4 NW / 3 NE + home-prefer emergency only when idle
- quick: **37661.0** (margin 34263.0, errors 0, std 2433.3) — still **−1046** vs baseline.

## Eval: contiguous row-band ownership (sweep NW_UNIT_COUNT)
- NW=2 row-bands: **39528.8** (+821 vs baseline) ← best
- NW=3 row-bands: **39216.9**
- NW=4 row-bands: **38285.2**
- NW=5: **38338.2**; NW=6: **37303.1**; NW=1: **38014.2**
- Column bands NW=2: **39120.1** (worse than rows)
- Modulo within-quad NW=2: **38541.4** (worse than row bands)
- Insight: NE carrot fill needs most of the hands; NW melons need only a small watering crew. Contiguous strips beat scatter.

## Final config selection
- NW=2 row-bands: quick **39528.8**; validation **37039.4** (+456 vs parent 36584)
- NW=3 row-bands: quick **39216.9**; validation **37329.4** (+746 vs parent) ← **final**
  (hypothesis example units 0..2 NW / 3..6 NE; better validation transfer than NW=2)
- Reconfirmed NW=3 quick: **39216.9**. Validation: **37329.4** (+746 vs parent 36584; also > n004 36892).
- HANDOFF.md + proposals.json written. Final commit hash recorded in HANDOFF.
