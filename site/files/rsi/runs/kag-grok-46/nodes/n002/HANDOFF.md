# Handoff n002: Early daily HIRE for wheat throughput
## Hypothesis
Keep a simple crop (WHEAT) but each morning (hour==0) issue as many HIRE orders as cheap Fibonacci costs allow (5 hands, $12/day while cash>reserve), then assign farmer+hands to disjoint tiles: plant empties, water unwatered plants, harvest at max_yield_day, and DROP/SELL produce. Labor is the bottleneck for >1 tile; 6 actors/day can tend the whole NW 5×5.
## What I did
- Replaced the single-carrot starter in `agent.py` with `decide(obs)` from `src/policy.py`.
- `src/constants.py`: CROP=WHEAT, MAX_HANDS=5, HIRE_CASH_RESERVE=300, fib hire costs, TILES_PER_ACTOR=5.
- `src/grid.py`: pathing, shed helpers, unit positions/inventories.
- `src/policy.py`: hour-0 HIRE, BUY_SEED wheat, SELL shed; exclusive greedy targets with stay-on-tile so each actor finishes water→harvest→replant→water before walking; never plant at hour 23 (new plants must be watered the same day).
- Hands hired at hour 0 first act at hour 1 (market runs after unit actions). Action list length always matches `hands`.
## Result
- untouched quick: score 3491.3 (12 games, errors=0)
- quick: score 15888.33 (was 3491.3); margin 12293.5; win_rate 1.00; errors 0; std 715.4; min 15250 max 17437. Command: `eval/eval.py --seedset quick`
- validation: score 16216.75 (was 3586.81 at root); margin 12609.25; win_rate 1.00; errors 0; std 1207.65; min 15064 max 18375; n_games 32. Command: `eval/eval.py --seedset validation`
- git: `da8b7b89d41ce69023ab8596855402e1efad44ad`
## Mechanism
Hire cost is tiny (1+1+2+3+5=$12) and resets daily, so 6 actors × 23 turns ≈ 138 actions/day vs the baseline's 24. That is enough to plant, water daily, and harvest all 25 NW wheat tiles. Wheat's unfertilized peak is 4 units at age 4 (base 1 + bonus water ages 2–4); glut curve is log/0.20 so dumping ~90–100 units per cycle still pays ~$20–25. Same-day replant keeps a 5-day cycle (plant day 0, harvest/replant 4, 8, …). Starter only loops one carrot, so we win every game on this opponent.
## Dead ends
- Stride partitions (tiles[i::n]): actors zigzag across the 5×5; harvest days left weeds (seed 101 ≈ 14751).
- Compact row partitions with a left-column hand: that hand spawned on a locked shed tile and spent too many turns walking (seed 101 ≈ 14957, still 2 weeds).
- Greedy matching that capped 24 plant jobs in row-major order dropped (4,4); farmer spawned on fallow every morning (seed 101 ≈ 14488).
- Water-the-whole-field-before-harvest: delayed replant by a day, broke the 5-day cycle (seed 101 15643 → 14659). Stay-and-finish the current tile is required for same-day replant.
## Next hypotheses
- Buy NE (then SW) once bank exceeds ~$4000 and run the same 6-actor wheat loop on 50 tiles; hire 6–8 hands (next fib costs 8, 13) so harvest-day 4-step chains still finish.
- Spend bonus-window days fertilizing wheat (bought fertilizer or 2–3 geese for free fertilizer + eggs) to lift unfertilized 4-yield to the cap of 6.
- After land, mix in carrots (4-day cycle, pet-cafe demand) on a subset of tiles while keeping wheat as the glut-tolerant bulk crop.
## Open questions
- Harvest days still leave ~1–3 ripe tiles at hour 23 (6 actors × 23 turns is tight for 25 tiles × 4 actions plus spawn walking). Would 6–7 hands close that gap without idle-labor waste on watering-only days?
- End-of-day auto-drop + next-morning SELL works (shed cap 100, we sell ~88–96 wheat/cycle). Same-day DROP into town ticks (every 4 turns) might capture slightly better prices.
- Last plant day is 25 (max_yield_day=4, season day 29). Day 28–29 still have leftover ripe plants that are not always collected.
