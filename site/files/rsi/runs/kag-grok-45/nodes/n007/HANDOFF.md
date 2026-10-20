# Handoff n007: More hands after NE unlock
## Hypothesis
Keep BUY_LAND NE (day≥10, melon cap 16) but raise TARGET_HANDS from 6 to 8–10 once NE is unlocked (or always hire 8 after day 10). Extra actors should fill the ~20–30 persistent empty tiles with carrot and cut weed losses; hire fib cost is still tiny vs crop revenue. n002’s TARGET=8 failure was on 25 tiles only, so 50 tiles might need more labor.

## What I did
- `src/farm_ops.py`: added `BASE_HANDS=6`, `POST_LAND_HANDS` (swept 7–10), `HANDS_SCALE_MODE` (`unlock` vs `day`), and `target_hands(farm, day)`.
- `src/market.py`: hire to `target_hands`; early-cap at BASE before BUY_LAND so the land order fits in the 10-slot market budget; same-turn top-up after unlock; seed buys use the dynamic want.
- `agent.py`: docstring for n007 hypothesis.
- Quick sweep of POST_LAND_HANDS ∈ {7,8,9,10} and day vs unlock gating; final knobs `POST_LAND_HANDS=7`, `HANDS_SCALE_MODE=unlock`.

## Result
- Untouched parent quick: score **38707.5** (`eval/eval.py --seedset quick`).
- Best worker quick: score **38894.3** with POST=7 unlock-gated (margin 35459.9, win_rate 1.00, errors 0, std 2369.0).
- Hypothesized 8–10 all worse on quick: 8→38004.4, 9→36568.9, 10→35547.8; day-gated 8 identical to unlock 8.
- Validation (POST=7): score **36405.2** (margin 33065.9, win_rate 1.00, errors 0, std 3068.9, n_games 32) — `eval/eval.py --seedset validation`.
- Parent validation was 36583.7; this node is a **regression (~−178)**. Hypothesis did not improve the official metric; 8–10 are clearly harmful.
- Final git commit: `d987f9507ae6c98e064137371844810bde86e1ee`.

## Mechanism
NE unlock still leaves empties, but adding hired hands under the same board-index `% n_units` partition does not convert those empties into net money. Extra units further scatter tile ownership across non-contiguous NW+NE, so pathing and unfinished seed cycles eat the fib-cheap labor; melon watering (16 long-cycle tiles) is diluted rather than carrot fill improving. The only mild quick lift was +1 hand (7), and even that overfit — validation dropped. Confirms n003’s “more hands after NE hurt” finding under the melon+carrot economy as well: land expansion remains bandwidth-gated by *how* labor is assigned, not by hire count alone.

## Dead ends
- POST_LAND_HANDS=8 (unlock or day): quick 38004.4 < baseline 38707.5.
- POST_LAND_HANDS=9: quick 36568.9.
- POST_LAND_HANDS=10: quick 35547.8.
- POST_LAND_HANDS=7: quick 38894.3 but validation 36405.2 < parent 36583.7.
- Seed-before-extra-hire reorder: abandoned (mornings with 2 SELLs leave no market slots for the extra HIREs).

## Next hypotheses
1. Quadrant-local partition: assign some units exclusively to NE and some to NW so pathing stops crossing the shed gap under index-mod (labor reallocation without raising hire count).
2. Melon fertilizer (BUY_PRODUCT or goose) on ages 6–8 to hit yield 6 by age 8 — free two days per cycle so the same 6 hands can cover carrots.
3. Revert NE land (or delay further) and spend the $1000 + labor on fertilizer/animals on NW-only — land may be strictly negative until partition is fixed.

## Open questions
- Does a contiguous NE-only vs NW-only unit split fix empties without the scatter tax that killed hands 8–10?
- Can fertilizer shorten melon duty enough that BASE_HANDS=6 covers 50 tiles, making land finally positive?
- Is SW ever worth testing, or is any acreage expansion doomed until assignment changes?
