# n002 progress

## Hypothesis
Early daily HIRE (hour==0) of 3–5 hands at Fibonacci cost, keep a simple crop (WHEAT), partition tiles across farmer+hands: plant / water / harvest / DROP.

## Plan
- Confirm untouched quick score.
- Implement: morning HIRE, wheat on NW 5x5, fixed partitions, water-every-day, harvest at max_yield_day, sell from shed.
- Iterate on quick, then validation.

## Log

### 2026-09-10 start
Read docs/RULES, GETTING_STARTED, env source (kaggriculture.py).
Key mechanics:
- Hire cost fib(n): 1,1,2,3,5 → 5 hands = $12/day. Hands vanish end of day.
- HIRE is a market order; unit actions run *before* market, so hands hired at hour 0 first act at hour 1.
- First hands spawn on locked shed-adjacent tiles (passable, cannot plant/water there).
- Atomic PLANT: if plant requests for a crop exceed seeds, *all* those PLANTs become PASS.
- Wheat unfertilized: base 1 + bonus water ages 2–4 = 4 units. Must water plant day (consecutive_unwatered starts at 1).
- End-of-day inventory auto-drops to shed (cap 100). SELL is from shed after DROP / eod drop.

Crop choice: WHEAT (cheap seed, glut-tolerant log curve). Cap 5 hands as hypothesized.

Running untouched quick eval next.

### Untouched baseline
quick: score=3491.3 (12 games, std=77.4, errors=0)

### Implementation v1 (stride partitions, 5 hands, wheat, 25 tiles)
Seed 101 seat 0: $14,751. Harvest-day walking too high; some tiles missed water → weeds.

### v2 compact row partitions, 24 tiles
Seed 101: $14,957. Left-column hand walks 5 tiles onto locked spawn; still 2 weeds on harvest nights.

### v3 greedy exclusive matching
Worse ($14,488): plant-job sort dropped (4,4), farmer spawned on fallow every morning.

### v4 stay-on-tile + plant nearest-to-shed first, cap 25
Seed 101: $15,643. Full 25 wheat, 0 weeds through day 9, ~96 units sold per harvest cycle.

### quick eval of v4
`eval/eval.py --seedset quick` → score=15888.33 margin=12293.5 win_rate=1.00 errors=0 std=715.4 min=15250 max=17437 n=12 git=8652bbe
Baseline quick was 3491.3. ~4.55×.

### v5 water-all-first (aborted)
Seed 101: $14,659. Harvest-then-replant slipped a day, desynchronized cycles. Reverted to v4 stay-on-tile.

### validation
`eval/eval.py --seedset validation` → score=16216.75 margin=12609.25 win_rate=1.00 errors=0 std=1207.65 min=15064 max=18375 n=32 elapsed=12.8s git=da8b7b89d41ce69023ab8596855402e1efad44ad

Root was 3586.81. Hypothesis confirmed: morning HIRE + wheat on 25 tiles is ~4.5× the solo carrot loop.

Wrote HANDOFF.md and proposals.json.
