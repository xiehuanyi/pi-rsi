# n006 progress

Hypothesis: Compact spawn-aware 5x10 regions. After NE unlock, replace greedy fallback matching with compact row/block partitions over unlocked tiles only. Keep stay-on-tile. Farmer (4,4) and first hand (5,4) keep spawn rows. Do not buy SW.

## Plan
1. Measure untouched parent (n003 NE wheat + 8 hands, greedy stay-on-tile) on quick.
2. Diagnose leftover ripe/unwatered tiles and spawn walking on a 5x10 harvest day.
3. Replace `_greedy_targets` fallback with spawn-aware compact regions (stay-on-tile kept; greedy leftover so far tiles still finish). Use regions only once NE is unlocked (n002 found compact rows worse on 5x5).
4. Iterate on quick, then validation.

## Log

### 2026-09-10 start
Read parent `src/policy.py` `_greedy_targets`, `src/grid.py` leftover `partition_tiles`/`NW_BLOCKS`, spawn rules.

Spawn with 8 hands (hour 1): farmer (4,4); hands (5,4),(4,5),(5,5),(4,4),(5,4),(4,5),(5,5),(4,4). After NE, (4,4)/(5,4) are plantable; (4,5)/(5,5) stay locked so 4 hands spend the first step walking onto NW/NE.

n002 dead end: stride and compact-row partitions on the 5x5 left weeds. Hedge: keep greedy on NW-only; switch to spawn-aware rows once the 5x10 is online.

About to run untouched quick baseline.

### Untouched baseline
- quick: score 22343.1 (12 games, errors=0, std=179.2, margin=18789.3, win_rate=1.00, min/max from parent). Command: `eval/eval.py --seedset quick`
- Matches n003 parent (22343.1).

### Diagnose seed 101 (parent greedy)
- Final $22454 vs starter $3560.
- Hour-23 leftover ripe: 0 every day. Leftover unwatered on harvest/plant-NE days: d5:3, d8:4, d9:4, d12:4, d13:5, and the same 4–5 pattern each cycle. Weeds appear the morning after (d10, d14, d26, d29).
- After NE, 4 of 9 actors spawn on locked (4,5)/(5,5). Greedy + x-first pathing sends (4,5) WEST into locked SW instead of NORTH onto the field.
- Day 5 h1 first hand WEST off plantable (5,4): land-buy morning fills the 10-order cap with SELL+LAND+8 HIRE, so no extra seeds that hour (known n003 dead end; not this node).

Mechanism to hit: compact regions so locked-spawn hands walk NORTH onto their spawn-side rows, stay-on-tile sweeps the row, leftover greedy still covers overflow (NE harvest 7 tiles × 4 actions > 23 turns).

### v1 exclusive 5x10 row chunks (seed 101 seat 0)
Farmer row y=4 NW (5 tiles), first hand y=4 NE + 2 (7 tiles), remaining actors equal chunks shed-outward. Stay-on-tile + leftover greedy.
- FINAL $21118 (parent $22454). Harvest days left ripe tiles (d8:4 ripe+5 uw, d9:7 ripe+8 uw). Exclusive rows send y=0 actors on 4–5 step morning walks; NE 4 actors × 7-tile harvest chains overrun 23 turns and cannot borrow labor until their region is empty.

### v2 exclusive NW/NE side blocks (seed 101)
Even actors NW, odd NE, home-row tie-break, leftover greedy.
- FINAL $20849. Worse. 4 NE actors cannot finish 25×4 harvest actions (100 > 92). Watering-only side only helps after its 25 waters.

### v3 soft SIDE_PENALTY
- penalty=2 + home rows: $21132, weeds on d9
- penalty=1 no home rows: $21739, still leftover ripe and weeds
Soft locality still delays help to the harvest half.

### v4 spawn strips
- Farmer/first-hand pinned to spawn row y=4: $21568. Farmer walks WEST along the row instead of greedy-nearest (often NORTH).
- Locked SW/SE only, exclusive spawn column: $21919. Closer; still leftover ripe.
- Column job only if not farther than global nearest, else NORTH to entry: $22129. Best of the region variants, still below parent $22454.

Parent leftover is 4–5 unwatered with 0 leftover ripe. Every compact partition left more unfinished work. Greedy stay-on-tile already takes nearest shed-adjacent jobs; exclusive/soft regions mainly stop labor from crossing onto the harvest-heavy half.

Shipping v4 locked-spawn columns (least-bad on-hypothesis change): stay-on-tile, locked (4,5)/(5,5) match spawn column x=4/x=5 else walk NORTH to (4,4)/(5,4), everyone else greedy. Farmer/first-hand keep spawn rows via stay-on-tile.

About to run quick eval.

### quick (shipped v4 locked-spawn columns)
- quick: score 21815.2 (was 22343.1); margin 18289.8; win_rate 1.00; errors 0; std 170.6; elapsed 8.2s. Command: `eval/eval.py --seedset quick`
- Regression of ~$528 vs parent greedy stay-on-tile. Hypothesis not confirmed on quick.

About to run validation.

### validation (shipped v4)
- validation: score 21683.1 (was 22269.0 at n003); margin 18081.7; win_rate 1.00; errors 0; std 239.4; min 21249 max 21962; n_games 32; elapsed 15.9s. Command: `eval/eval.py --seedset validation`
- git: `967d3d19e3e7e6b9604c05811fe502218e55f2ee`

Hypothesis refuted: compact spawn-aware regions (exclusive rows, side blocks, soft penalty, spawn columns) all scored below parent greedy stay-on-tile. Parent already finishes all ripe tiles; leftover is 4–5 unwatered, likely hour-21 DROP not zigzag. Do not retry partitions.
