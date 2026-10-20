# Handoff n005: Fertilize wheat bonus window via spawn-tile geese
## Hypothesis
50 NW+NE wheat tiles still peak at 4 unfertilized. During ages 2–4, FERTILIZE then WATER adds 2/day instead of 1 (cap 6). Place 2 geese on coops at the shed-access spawn tiles (BUILD_COOP, BUY_ANIMAL GOOSE, PLACE, daily FEED from own wheat, COLLECT_FERTILIZER, CARE) rather than BUY_PRODUCT FERTILIZER at $100. Apply one fertilizer per plant covering the 3-day bonus window. DROP at 12 on non-stay-on-tile actors so 6-yield harvests can SELL before the 100-cap shed overflows.
## What I did
- `src/constants.py`: NUM_GEESE=2, COOP_SITES=(4,4)/(5,4), FEED_WHEAT_RESERVE=10, DROP_INVENTORY_THRESHOLD=12.
- `src/animals.py` (new): coop jobs, goose buy/place, FEED/COLLECT/CARE, fertilize-window targeting, wheat sell reserve, shed pickups.
- `src/policy.py`: never plant coop sites; FERTILIZE before WATER when the unit holds fertilizer; SELL skips fertilizer/animals and reserved feed wheat; BUY_ANIMAL GOOSE only when an empty coop slot exists; emergency BUY_PRODUCT WHEAT only if total wheat is 0; stay-on-tile still beats DROP.
- `src/grid.py`: `item_count`.
- `agent.py`: still `agent(obs) -> decide(obs)` with fail-closed PASS.
## Result
- untouched quick: score 22343.1 (12 games, errors=0). Command: `eval/eval.py --seedset quick`
- v6 quick: score 23286.6 (was 22343.1); margin 19618.1; win_rate 1.00; errors 0; std 318.9; min 22849 max 23740. Command: `eval/eval.py --seedset quick`
- validation: score 23597.9 (was 22269.0 at n003); margin 19941.1; win_rate 1.00; errors 0; std 556.7; min 22665 max 24469; n_games 32. Command: `eval/eval.py --seedset validation`
- git: `d8bc54481fdb0a5695f5fd269194d5019bb065f7`
## Mechanism
Two coops sit on the spawn/shed-access tiles, so morning FEED and COLLECT_FERTILIZER do not require a long walk. Each goose yields 1 fertilizer/day; FERTILIZE before WATER on an age-2–4 wheat plant doubles the bonus for three days and lifts that tile from 4 to 6 wheat. Eggs (with CARE) add a second product that still sells near $40–50 on the log glut curve. A 10-wheat shed reserve feeds the geese from our own harvest after day 4, so we do not buy $25 market wheat every morning. DROP at 12 after finishing the current tile lets mid-harvest SELL clear the shed; stay-on-tile still completes the water→harvest→replant→water chain.
## Dead ends
- Daily BUY_PRODUCT WHEAT whenever shed < n_geese (v1): pickup of the reserve immediately triggered another buy; ~$50/day wasted. Seed 101 23633 with this bug; removing it (v6) is the shipped agent.
- Buying a second goose on day 0 before (5,4) exists: $300 sat in the shed until NE and delayed the land buy.
- Delay all geese until after NE, DROP 24, skip CARE (v2): seed 101 21501. Coop tiles stole DROP/water actions; NE was on time but watering slipped.
- Assigned-only coop actions (v3): seed 101 16847. Fertilizer dumped to the shed at EOD and almost never picked up (9 FERTILIZE vs 53 COLLECT).
- Anyone-on-coop without CARE, DROP 24 (v4): seed 101 21553. Double FEED no-ops (106 vs ~56) stole harvest-day labor.
- Third goose on (4,3) (not shed-adjacent): seed 101 20104. Geese escaped, 4 BUY_ANIMAL / 6 BUILD_COOP; feeding the off-shed coop is unreliable.
## Next hypotheses
- Skip or defer CARE (and egg HARVEST) on 25-ripe harvest days so the 8 hands finish watering; seed 101 still left 4–10 tiles unwatered at hour 23.
- Compact spawn-aware regions on the 5×10 NW+NE strip so locked SW/SE spawn tiles waste fewer morning walks and harvest leftovers close.
- Mix carrots on a shed-adjacent subset once PET_CAFE / FARMERS_MARKET is in `town.unlocked_shops`, keeping wheat as the glut-tolerant bulk crop.
## Open questions
- Two fertilizer/day covers only ~2 of ~10 plants that enter the age-2 window; is the rest of the +$1.3k validation gain eggs+CARE rather than wheat yield?
- Would one extra hand (fib $34) pay if it only exists to finish the 4–10 unwatered leftovers on harvest days?
- Last plant day is 25; day 28–29 leftover ripe plants and last-day EOD shed wheat may still miss a SELL turn.
