# Handoff n006: Compact spawn-aware 5x10 regions
## Hypothesis
After NE unlock, greedy nearest still zigzags the 5×10 strip and 3 of 8 hands spawn every morning on locked SW/SE shed tiles (4,5)/(5,5) and spend the first step walking. Replace _greedy_targets with compact row/block partitions over unlocked tiles only, farmer on (4,4) and first hand on (5,4) keeping their spawn rows. Goal: finish leftover ripe/unwatered tiles on harvest days without buying SW.
## What I did
- Measured parent greedy stay-on-tile: seed 101 leaves 0 ripe at hour 23 but 4–5 unwatered on harvest days; after NE, 4 of 9 actors spawn on locked (4,5)/(5,5).
- `src/grid.py`: `spawn_strip` / `spawn_entry` — locked SW/SE keep spawn column x=4 / x=5 so the first step is NORTH onto (4,4)/(5,4).
- `src/policy.py`: `_region_targets` keeps stay-on-tile, matches locked-spawn actors to that column (else walk to the entry tile), then parent greedy leftovers. Farmer and first hand keep spawn rows via stay-on-tile. `_greedy_targets` still used as the non-shed path.
- `src/constants.py`: SPAWN_NW/NE/SW/SE. Did not buy SW.
- Tried and reverted internally: exclusive 5×10 row chunks, exclusive NW/NE side blocks, soft SIDE_PENALTY 1–2, pinning farmer/first-hand to y=4.
## Result
- untouched quick: score 22343.1 (12 games, errors=0). Command: `eval/eval.py --seedset quick`
- seed 101 seat 0 parent: $22454, 0 leftover ripe, 4–5 unwatered on harvest nights.
- seed 101 exclusive 5×10 rows: $21118; side blocks: $20849; SIDE_PENALTY=2: $21132; SIDE_PENALTY=1: $21739; farmer spawn-row pin: $21568; locked-column strips: $21919.
- quick (shipped locked-column strips): score 21815.2 (was 22343.1); margin 18289.8; win_rate 1.00; errors 0; std 170.6; min 21435 max 21962. Command: `eval/eval.py --seedset quick`
- validation: score 21683.1 (was 22269.0 at n003); margin 18081.7; win_rate 1.00; errors 0; std 239.4; min 21249 max 21962; n_games 32. Command: `eval/eval.py --seedset validation`
- git: `967d3d19e3e7e6b9604c05811fe502218e55f2ee`
## Mechanism
Parent greedy stay-on-tile already finishes every ripe wheat tile on the 50-tile stagger. The 4–5 leftover unwatered plants are not from zigzag across the strip. Exclusive compact rows/blocks trap 4 NE actors on 25 harvest chains (100 actions > 4×23) while the NW side is watering-only, so ripe tiles and weeds appear. Soft side penalties delay the same cross-strip help. Forcing locked SW/SE spawns NORTH onto the spawn column avoids walking WEST into locked land, but it also claims column jobs that greedy would have given to a closer actor, and the extra constraint still missed more waters than parent. Stay-on-tile plus nearest remaining job is the better 9-actor matcher on this field.
## Dead ends
- Exclusive 5×10 row chunks (farmer y=4 NW, first hand y=4 NE, extras shed-outward): seed 101 $21118; d8 leftover 4 ripe + 5 unwatered (parent 0 ripe + 4 unwatered).
- Exclusive NW/NE side blocks (even/odd actors): seed 101 $20849. 4 actors cannot finish a 25-tile 4-step harvest.
- Soft SIDE_PENALTY=2: $21132; penalty=1: $21739. Still leftover ripe and weeds.
- Pinning farmer and first hand to spawn row y=4: $21568. Farmer walks WEST along the row instead of greedy-nearest (often NORTH).
- Locked-spawn columns only (shipped): quick 21815.2 vs parent 22343.1; validation 21683.1 vs 22269.0.
## Next hypotheses
- Skip hour-21 DROP while unwatered (or ripe) tiles remain: parent leftover is 4–5 unwatered, 0 ripe; DROP_LATE_HOUR=21 sends all carriers to the shed for hours 21–23 (~27 actions), which can explain the missed waters without touching matching.
- Fertilize wheat's bonus window (ages 2–4) with 2–3 geese and forced morning PICKUP so fertilizer actually leaves the shed (n004's failure mode); pair with DROP only when idle so harvest chains are not interrupted.
- Mix carrots on a shed-adjacent subset once PET_CAFE / FARMERS_MARKET is in `town.unlocked_shops`, keeping wheat as the glut-tolerant bulk crop.
## Open questions
- Are the parent 4–5 leftover unwatered tiles always the last greedy jobs, and do they sit in one quadrant or scattered?
- Would y-first (not x-first) stepping from locked (4,5)/(5,5) recover the NORTH first step without claiming a column job?
- Last plant day is 25; day 28–29 leftover ripe may still not all DROP/SELL.
