# Handoff n010: Fertilize wheat bonus window
## Hypothesis
50 NW+NE wheat tiles still peak at 4 unfertilized. During ages 2–4, FERTILIZE then WATER adds 2/day instead of 1 (cap 6). Place 2 geese on coops at the shed-access spawn tiles (BUILD_COOP, BUY_ANIMAL GOOSE, PLACE, daily FEED from own wheat, COLLECT_FERTILIZER) rather than BUY_PRODUCT FERTILIZER at $100. Force morning PICKUP of fertilizer so it actually leaves the shed. Apply one fertilizer per plant covering the 3-day bonus window. DROP/SELL when idle or hour>=21 with no remaining WATER jobs; overflow DROP at 12 only on non-stay-on-tile actors so 6-yield harvests can SELL before the 100-cap shed overflows.
## What I did
- `src/constants.py`: NUM_GEESE=2, COOP_SITES=(4,4)/(5,4), FEED_WHEAT_RESERVE=10, DROP_INVENTORY_THRESHOLD=12, WHEAT_BONUS_START=2.
- `src/animals.py` (new): coop jobs, goose buy/place, FEED/COLLECT/CARE, fertilize-window targeting, wheat sell reserve, shed pickups (forced morning PICKUP of fertilizer). Fail-closed on non-dict goose tiles (n004 None.get).
- `src/policy.py`: never plant coop sites; FERTILIZE before WATER when the unit holds fertilizer; SELL skips fertilizer/animals and reserved feed wheat; BUY_ANIMAL GOOSE only when an empty coop slot exists; emergency BUY_PRODUCT WHEAT only if total wheat is 0; stay-on-tile still beats DROP; hour>=21 DROP only if no WATER jobs remain. Replaced n006 spawn-strip matching with greedy stay-on-tile+nearest (spawn strips plus coop occupancy left ripe wheat).
- `src/grid.py`: `item_count`.
- `agent.py`: still `agent(obs) -> decide(obs)` with fail-closed PASS.
## Result
- untouched quick: score 21815.2 (12 games, errors=0). Command: `eval/eval.py --seedset quick`
- v5 quick: score 24122.6 (was 21815.2); margin 20501.2; win_rate 1.00; errors 0; std 280.6; min 23803 max 24663. Command: `eval/eval.py --seedset quick`
- validation: score 24574.6 (was 21683.1 at n006); margin 20902.5; win_rate 1.00; errors 0; std 714.3; min 23449 max 26182; n_games 32. Command: `eval/eval.py --seedset validation`
- seed 101 seat 0: $24139 (n006 parent $22454; n005 fertilizer baseline $23453). FERTILIZE=53 COLLECT=77 PICKUP_FERT=10 FEED=58 CARE=111. Geese stay fed; fertilizer leaves the shed.
- git: `51fa32118e629c9ce4d3391366d76bfa7bb19727`
## Mechanism
Two coops sit on the spawn/shed-access tiles, so morning FEED and COLLECT_FERTILIZER do not require a long walk. Each goose yields 1 fertilizer/day; FERTILIZE before WATER on an age-2–4 wheat plant doubles the bonus for three days and lifts that tile from 4 to 6 wheat. Eggs (with CARE) add a second product that still sells near $40–50. A 10-wheat shed reserve feeds the geese from our own harvest after day 4. Skipping the hour-21 mass DROP while unwatered tiles remain returns those actions to WATER (seed 101 WATER 1423 vs n005 1386, DIG 10 vs 14). Overflow DROP at 12 after stay-on-tile lets mid-harvest SELL clear the 100-cap shed. n006 spawn-column matching plus coop occupancy left ripe wheat; greedy stay-on-tile+nearest is the matcher that lets 9 actors finish harvest while 2 stand on geese.
## Dead ends
- Geese on n006 spawn-strips with n005 CARE/DROP (v1): seed 101 $20072; quick 21461.8. Fertilizer fired (FERTILIZE=48) but CARE=123 and leftover ripe (day 13: 8 unwatered + 4 ripe).
- Skip CARE / visitor wheat pickup (v2): seed 101 $18614. HARVEST 371→254; leftovers worse.
- Fertilizer ages 2–3 only + idle-only DROP (v3): seed 101 $18652. SELL WHEAT 39→28; day 14 weeds=5 from shed overflow and unharvested ripe.
- Those cuts plus greedy (v4): seed 101 $18534. Cutting CARE and overflow DROP was the damage, not matching alone.
- Third goose on (4,3) was not retried (n005: escaped, seed 101 $20104). Bought $100 fertilizer not run (negative ROI at glut wheat ~$22).
## Next hypotheses
- Defer CARE and non-cap egg HARVEST on a latched harvest day (ripe + same-day replants) while wheat still needs water/harvest/replant; keep FEED+COLLECT. Seed 101 still left 6–7 unwatered on peak days with CARE=111.
- Route DROP/PICKUP to locked SW/SE shed tiles (4,5)/(5,5) so harvest dumps never stand on goose coops.
- Exclusive homes only on far leftover columns, with shed-spawn actors fully greedy (n008 matcher on this fertilizer base).
## Open questions
- Two fertilizer/day covers only ~2 of ~10 plants that enter the age-2 window; how much of the +$2.9k validation gain vs n006 is extra wheat vs eggs vs fewer weeds from the late-DROP skip?
- Last plant day is 25; day 28 leftover plants (16 at hour 23) and last-day EOD shed wheat may still miss a SELL turn.
- Would a 9th hand (fib $34) on harvest-cohort days only finish the remaining 6–7 unwatered tiles without paying the fee on watering-only days?
