# Handoff n008: Quadrant-local hand partition
## Hypothesis
Replace flat board-index % n_units ownership with quadrant-aware assignment after NE unlock: units 0..2 own NW, units 3..6 own NE, each partitioned into contiguous row bands. Same TARGET_HANDS=6 and MELON_MAX_TILES=16. Goal: cut shed-gap cross travel and raise plant/water completion on both quadrants so the NE land buy from n005 finally pays.

## What I did
- `src/farm_ops.py`: added `tile_quadrant`, `unit_home_quadrant`, `nw_owner_count`, `owns_local_tile` (contiguous row bands); rewrote `owned_tasks` to use flat % n_units pre-NE and quadrant-local ownership post-NE.
- Kept emergency WATER/HARVEST/DIG when a unit has no owned tasks; prefer home-quadrant emergencies first.
- Tuned `NW_UNIT_COUNT` on quick (1–6) and checked validation for NW=2 vs NW=3; left TARGET_HANDS=6 / MELON_MAX_TILES=16 / BUY_LAND day-10 unchanged.
- `agent.py`: docstring updated for n008.

## Result
- Untouched parent quick: **38707.5** (`eval/eval.py --seedset quick`).
- Best worker quick: **39528.8** with NW_UNIT_COUNT=2 row-bands.
- Final (validation-preferred): NW_UNIT_COUNT=3 row-bands — quick **39216.9**; validation **37329.4** (margin 34021.3, win_rate 1.00, errors 0, std 2579.6, n_games 32) — `eval/eval.py --seedset validation`.
- Parent validation was 36583.7; this node is **+745.7**. Also above prior global-best n004 (36891.8, no NE land).
- Final git commit: `ab07b2cc2bddd5d8d08d5edf3d45edac626c0361`.

## Mechanism
Flat index-mod ownership scattered tiles across non-contiguous NW+NE, so hands spent turns crossing the shed gap and left NE empties idle. Hard quadrant homes keep most pathing inside one 5×5. Contiguous row bands beat within-quad modulo scatter. Staffing NE with 4 of 7 units (NW=3) fills carrot acreage while 3 NW units cover the 16-melon watering load; NW=2 filled NE even more on quick but under-served NW melons on the broader validation set.

## Dead ends
- NW=3 with local-index modulo (first try): quick **37004.4** (−1703 vs parent).
- Emergency WATER before PLANT (steal across quadrants while empties remain): quick **33989.0**.
- NW_UNIT_COUNT=4/5/6 row-bands: quick 38285 / 38338 / 37303 — all below parent.
- Column bands NW=2: quick **39120.1** < row bands.
- NW=2 (quick-best 39529): validation only **37039.4** < NW=3’s 37329.

## Next hypotheses
1. Melon fertilizer (BUY_PRODUCT or goose) on ages 6–8 to hit yield 6 by age 8 — free two days per cycle; with quadrant partition the same 6 hands may cover carrots better once melon duty shortens.
2. Soft quadrant preference instead of hard ownership: sort tasks by (home_first, distance) so idle NE hands plant locally but can assist NW water without waiting for zero owned tasks.
3. Delay or gate BUY_LAND until NW empties≤N under the new partition — avoid paying $1000 before the NW melon wave is fully staffed.

## Open questions
- Is 37329 the ceiling for NE+$6 hands, or does fertilizer unlock another +5–10k by cutting melon water days?
- Does hard ownership still leave ~some NE empties, or is fill now near-complete on validation seeds?
- Is SW ($2k) ever worth it once NE is fully utilized under quadrant partition?
