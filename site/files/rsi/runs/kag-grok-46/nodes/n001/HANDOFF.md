# Handoff n001: Multi-tile wheat farm with daily water/harvest route
## Hypothesis
Replace the single-tile carrot loop with a deterministic NW-quadrant wheat agent: buy seeds when cash allows, walk a fixed serpentine over unlocked empty tiles planting WHEAT, each day prioritize WATER on any plant with watered_today=False then HARVEST when age>=first_yield_day (or max_yield_day if time allows), DROP inventory at shed-adjacent tiles, and SELL all shed WHEAT every turn. Using ~20+ tiles and correct daily watering (bonus window ages 2–4) should raise mean money from ~3.5k toward tens of thousands with only farmer movement and market seed buys—no hands, land, or animals.
## What I did
- Replaced `agent.py` carrot loop with a thin wrapper around `src/wheat.py`.
- `src/wheat.py`: compact 4×2 patch of 8 tiles in the SE corner of NW (serpentine starting at spawn/shed `(4,4)`), bulk-buy a 4-seed wheat buffer, WATER every plant daily, HARVEST at age 4 (bonus window 2–4), cap new plants at 2/day so harvests do not clump, DIG weeds on work tiles, DROP only after field work, SELL all shed wheat every turn. Stop planting on day 26; harvest everything age≥2 on day 28 so EOD drop + day-29 SELL banks it.
- Constants live in `src/wheat.py` (`MAX_PLANTS=8`, `NEW_PLANTS_PER_DAY=2`, `HARVEST_AGE=4`).
## Result
- Baseline untouched starter: quick score 3491.3 (12 games, errors=0).
- Wheat farm: **quick: score 9360.67** (was 3491.3); min 8828 max 10055; win_rate 1.00; errors 0. Command: `eval/eval.py --seedset quick`.
- **validation: score 9524.62** (32 games vs starter); margin 5975.19; win_rate 1.00; errors 0; std 804.27; min 7338 max 10439. Command: `eval/eval.py --seedset validation`.
- Final git commit: `7ef83541749ae5dd55dbc8333fde2a9d0e6bea47`.
## Mechanism
Wheat at daily water and harvest-at-4 yields 4 units / 5 occupied days (base 1 + bonus on ages 2–4) for ~$90 gross minus $10 seed, vs the starter’s one carrot tile. Eight compact tiles next to the shed are the largest set one farmer can water *and* harvest+replant in 24 turns (2 harvests × 4 actions + 6 waters + 7 moves ≈ 21). Twenty daily-watered tiles is not feasible: watering N path-connected tiles costs 2N−1 actions, so water-only max is 12, and harvest+replant of a 3-plant cohort overflows 24 and misses waters (plants weed). Town wheat demand lifted late-game price into the 30s, so the 8-tile engine still beat the carrot loop ~2.7× and won every game. Headroom to 20k–50k needs more actors (hands), not a bigger solo route.
## Dead ends
- 9-tile 3×3 with a 3-plant ramp cohort: 3-harvest days need ~26 actions; missed 2 waters EOD, weeds, and day-29 harvests never reached the shed to DROP. Seed 101 seat 0 $7028 (below the 8-tile $8828).
- Skip watering age-1 plants (outside bonus window) to free turns for a 9th tile: seed 101 $9936 but seed 102 $7735 — a missed age-2 water after an age-1 skip weeds the plant. Reverted.
- Mid-route DROP while cargo is held: wastes a turn on the water/harvest path; EOD drop is enough except the last harvest day.
- Planting the full 25-tile NW serpentine with one farmer: cannot daily-water; weeds wipe the field.
## Next hypotheses
- Hire 1–2 farm hands each morning ($1, $1) and give each a disjoint compact wheat serpentine (another 8 tiles per hand). Same water-first / harvest-at-4 / 2-new-per-day rules. One farmer + two hands ≈ 24 tiles of daily-watered wheat — the original 20+ tile target — without buying land. Expected ~2–3× this node (~20k–30k) if they do not contend for seeds or the shed.
- After the wheat engine is printing cash, BUY_LAND NE ($1000) and run a hand on the NE 5×5 (shed-adjacent at `(5,4)`). More tiles only help once a second body exists.
- Do not skip to animals yet: unfertilized wheat is already action-bound, not cash-bound. Geese/coops want surplus wheat *and* extra actions for FEED/CARE; add them only after hands cover watering.
## Open questions
- Is harvest-at-3 (yield 3 / 4 days) ever better than harvest-at-4 once hands exist and tile count grows?
- Does selling wheat every turn vs holding for town-driven price spikes matter at this volume (T=400, we sell ~200/game)?
- First hire of the day spawns on locked `(5,4)` — does the hand path back into NW without wasting the first turns, or should we buy NE immediately so that spawn is usable?
