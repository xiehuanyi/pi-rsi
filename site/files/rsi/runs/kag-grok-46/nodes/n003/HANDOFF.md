# Handoff n003: Buy NE land and scale wheat
## Hypothesis
Once money exceeds ~$4000 (after the first wheat harvest around day 5), issue BUY_LAND for NE ($1000) then later SW ($2000). Keep the morning-HIRE wheat loop but raise MAX_HANDS to 7–8 and plant the new 25 tiles. Doubling the field should roughly double harvest volume; wheat's log glut curve still pays ~$19–20 at 2T. Reuse exclusive stay-on-tile targeting; hands already spawn on the NE shed tile (5,4) which becomes plantable after the unlock.
## What I did
- `src/constants.py`: MAX_HANDS=8 (fib $54/day), BUYABLE_LAND=("NE",), LAND_MIN_MONEY NE=4000, HIRE_CASH_RESERVE=600, DROP_INVENTORY_THRESHOLD=24 / DROP_LATE_HOUR=21.
- `src/policy.py`: `build_market` SELL then BUY_LAND (projected cash includes this-turn SELL) then HIRE then BUY_SEED; `_plant_budget` is every unlocked tile (+25 extra seeds the turn land unlocks); `choose_unit_actions` still stay-on-tile, and only walks to DROP when idle, hour>=21, or carrying >=24.
- `agent.py`: still `agent(obs) -> decide(obs)` with fail-closed PASS.
- Did **not** buy SW in the shipped agent (see Dead ends).
## Result
- untouched quick: score 15888.3 (12 games, errors=0). Command: `eval/eval.py --seedset quick`
- quick v1 (NE+SW, 7 hands, DROP at 12): score 19436.0. Command: `eval/eval.py --seedset quick`
- quick v2 (NE only, 8 hands): score 22343.1 (was 15888.3); margin 18789.3; win_rate 1.00; errors 0; std 179.2; min 21939 max 22483. Command: `eval/eval.py --seedset quick`
- validation: score 22269.0 (was 16216.75 at n002); margin 18708.3; win_rate 1.00; errors 0; std 235.6; min 21767 max 22483; n_games 32. Command: `eval/eval.py --seedset validation`
- git: `c23113bcc9578e6c35693e7c52ea007312cef2f5`
## Mechanism
First harvest (~day 4) plus morning SELL pushes the bank over $4000. BUY_LAND unlocks NE the same turn (market runs after unit actions), so hour 1 the (5,4) spawn is plantable and 25 new empties appear. Planting NE a day later than NW staggers the 5-day wheat cycle, so harvest days are ~25 ripe tiles rather than 50 — 9 actors can water 50 tiles easily and can mostly finish a 25-tile 4-step harvest chain. Wheat still sells ~$20 on the log glut curve. SW was skipped because the $2000 is deducted from the score and 75 tiles leave plants unwatered.
## Dead ends
- NE+SW, MAX_HANDS=7, DROP_THRESHOLD=12: quick 19436.0. Mid-harvest DROP trips left 6–11 plants unwatered; SW added ~8 tended tiles for $2000 and extra weeds. Seed 101 = 19491.
- SW at $6500 with 8/9/10/12 hands on seed 101: 21539 / 21841 / 21227 / 21227 vs NE-only 22454. More hands do not make SW pay for itself.
- BUY_SEED before HIRE so land-buy morning still buys seeds: quick 22252.2 (was 22343.1). That morning then only fits 7 HIRE under the 10-order cap; missing the 8th hand for the new-field day is worse than buying the extra seeds at hour 1.
- MAX_HANDS=6 or 7 on NE-only (seeds 101–103 mean): 19977 / 21521 vs 22294 for 8 hands. The 8th hand (fib $21) is worth it on 50 tiles.
## Next hypotheses
- Fertilize wheat's bonus window (ages 2–4) now that 50 tiles are online: watering alone caps at 4, fertilizer reaches 6. Prefer 2–3 geese (coop + COLLECT_FERTILIZER + eggs) over $100 BUY_PRODUCT fertilizer. Will overflow the 100-cap shed, so pair with mid-day DROP/SELL.
- Compact spawn-aware regions on the 5×10 NW+NE strip so locked SW/SE spawn tiles waste fewer morning walks and harvest leftovers close.
- Mix carrots on a shed-adjacent subset once PET_CAFE / FARMERS_MARKET is in `town.unlocked_shops`, keeping wheat as the glut-tolerant bulk crop.
## Open questions
- Do 8 actors still leave ripe tiles at hour 23 on 50-tile harvest days, or did stagger + the extra 2 hands close n002's 1–3 leftover gap?
- Last plant day is 25; day 28–29 leftover ripe plants may not all be collected and last-day EOD shed wheat may not get a SELL turn.
- Would a plant cap of ~n_actors×6 let SW ever pay, or is the $2000 better left in the bank until a different crop/animal uses the quadrant?
