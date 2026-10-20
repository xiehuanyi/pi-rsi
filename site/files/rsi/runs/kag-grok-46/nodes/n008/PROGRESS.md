# n008 progress

Hypothesis: Compact spawn-aware NW+NE regions. Partition the 5×10 unlocked strip into compact stay-on-tile regions that start at spawn tiles (4,4) and (5,4), so morning walks and harvest leftovers stay close. Locked SW/SE shed tiles currently waste steps.

## Plan
1. Measure untouched n005 parent on quick.
2. Diagnose seed 101 leftovers, spawn positions, and x-first walks off locked (4,5)/(5,5). n006 (on n003, no geese) already refuted exclusive rows/sides/columns; this node has coops on (4,4)/(5,4) so geometry differs. Do not retry exclusive no-overflow partitions.
3. Implement compact regions grown from spawn, keep exclusive stay-on-tile, allow overflow so harvest labor can cross. Prefer NORTH onto the field from locked SW/SE.
4. Iterate on quick, then validation.

## Log

### 2026-09-10 start
Read agent, policy, grid, animals, n005/n006 handoffs. `partition_tiles` / `NW_BLOCKS` exist but policy uses global `_greedy_targets`. n006 leftover on n003: 0 ripe, 4–5 unwatered; exclusive partitions left ripe+weeds. n005 leftover: 4–10 unwatered on seed 101 (CARE steals labor).

About to run untouched quick baseline.

### Untouched baseline
- quick: score 23286.6 (12 games, errors=0, std=318.9, margin=19618.1, win_rate=1.00, min=22849 max=23740). Command: `eval/eval.py --seedset quick`
- Matches n005 parent (23286.6). git `d8bc544`.

### Diagnose seed 101 seat 0 (parent greedy)
- Final $23453.
- Hour-1 spawns always: farmer (4,4); hands (5,4),(4,5),(5,5),(4,4),(5,4),(4,5),(5,5),(4,4). After NE, 4/9 actors on locked (4,5)/(5,5).
- Locked hour-1 moves mix NORTH (good) with WEST/EAST into locked SW/SE (x-first pathing).
- Hour-23 leftovers cluster on far edges, not near the shed: (0,3)×9, (0,1)×6, (0,2)/(1,0)/(1,1)/(9,4)×5, plus (0,0),(2,0),(8,4),(9,0),(9,2),(9,3). Day 8: 6 unwatered + 6 ripe on far NW, then weeds at (0,0)/(1,0)/(0,2).
- Mechanism to hit: give locked-spawn actors compact far-edge homes grown from (0,0)/(9,0); shed-spawn actors compact homes grown from (4,4)/(5,4); stay-on-tile + leftover greedy overflow; y-first onto unlocked from locked tiles. Not n006 exclusive rows/sides (those understaffed harvest).

About to implement v1.

### v1 seed 101 (full spawn-outward columns, exclusive then leftover greedy, y-first off locked)
- seed 101 seat 0: $24647 (parent $23453). Locked hour-1 all NORTH.
- Day 8 still 7 uw + 8 ripe on far NW; leftover hotspot moved to unassigned x=7. Full exclusive homes starve the unassigned column and understaff harvest (n006).
- Actor 6 BFS blobs were disconnected; switched to explicit columns.

### v1b full columns + x=7 on actor 5 + skip-coop for far walkers
- seed 101: $23388 (below parent). 10-tile exclusive NE home cannot finish a harvest chain.

### v2 far-edge homes only (locked SW/SE own x=0,1,8,9; shed-spawn greedy) + skip-coop + y-first
- seed 101 seat 0: $24861 (parent $23453, +1408). Still some far leftovers on harvest days (walk + 4-step chain does not cover 5 ripe tiles) but greedy bulk keeps harvest staffed.
- This is the on-hypothesis design that avoids n006 exclusive understaffing.

About to run v2 on quick.

### v2 quick
- quick: score 24974.6 (was 23286.6); margin 21445.2; win_rate 1.00; errors 0; std 261.9; min 24652 max 25364; n_games 12. Command: `eval/eval.py --seedset quick`
- Gain +1688 vs parent. Shipping this; full exclusive columns were worse.

About to run validation.

### v2 validation
- validation: score 24613.6 (was 23597.9 at n005); margin 21015.7; win_rate 1.00; errors 0; std 752.0; min 23519 max 25798; n_games 32. Command: `eval/eval.py --seedset validation`
- git: `c41146a4c3f1067dd6d2f09fffcf0698a87a486f`
- Official mean +1016 vs parent. Hypothesis confirmed when exclusive homes are only the far leftover columns; full 5×10 exclusive columns still fail as in n006.
