# Handoff n008: Compact spawn-aware far-edge columns
## Hypothesis
Partition the 5×10 unlocked strip into compact stay-on-tile regions that start at spawn tiles (4,4) and (5,4), so morning walks and harvest leftovers stay close. Locked SW/SE shed tiles currently waste steps; n003 left this as the next spatial fix after scaling to 50 tiles.
## What I did
- Diagnosed parent leftovers on seed 101: hour-23 unwatered tiles cluster on far west/east edges (x=0/1 and x=8/9); 4/9 actors spawn on locked (4,5)/(5,5) and x-first pathing often walks WEST/EAST into locked land.
- `src/constants.py`: `SHED_SPAWNS` (NWSE hire order) and `COLUMN_HOME_ACTOR` mapping x=0,1,8,9 to locked-spawn actors 2,6,7,3.
- `src/grid.py`: `home_regions` / `region_targets` (stay-on-tile, then home column, then leftover greedy); `step_toward` prefers a step onto unlocked land from a locked tile (NORTH off (4,5)/(5,5)).
- `src/policy.py`: once NE is unlocked, use region matching instead of global greedy; locked-spawn far walkers skip coop CARE/FEED/PICKUP so they do not stall on (4,4)/(5,4) while walking to the edge. Stay-on-tile finish is unchanged.
- `agent.py`: still `agent(obs) -> decide(obs)` with fail-closed PASS.
- Did **not** bind shed-spawn actors to exclusive near columns (see Dead ends).
## Result
- untouched quick: score 23286.6 (12 games, errors=0). Command: `eval/eval.py --seedset quick`
- seed 101 seat 0 parent: $23453; v2 far-edge homes: $24861.
- v2 quick: score 24974.6 (was 23286.6); margin 21445.2; win_rate 1.00; errors 0; std 261.9; min 24652 max 25364. Command: `eval/eval.py --seedset quick`
- validation: score 24613.6 (was 23597.9 at n005); margin 21015.7; win_rate 1.00; errors 0; std 752.0; min 23519 max 25798; n_games 32. Command: `eval/eval.py --seedset validation`
- git: `ee85065366bc5a44979cf1c52bf8deec35120c34` (behavior measured at `c41146a4c3f1067dd6d2f09fffcf0698a87a486f`; follow-up commit is docstring only)
## Mechanism
Parent greedy stay-on-tile piles all 9 actors on shed-adjacent jobs, so the far west/east wheat columns are the ones left unwatered at hour 23. Four hands spawn on locked SW/SE every morning; x-first walking sends them deeper into locked land. Giving those four compact column homes on x=0/1 and x=8/9, walking NORTH onto the field first, and not stopping to CARE on the coop, puts a walker on the leftover edges without taking harvest labor away from the other five (who stay fully greedy). Exclusive stay-on-tile still finishes water→harvest→replant→water on whatever tile they reach. Full exclusive 5×10 partitions (n006, and v1 here) still understaff the harvest half.
## Dead ends
- Full spawn-outward columns for all 9 actors (exclusive then leftover greedy, y-first): seed 101 $24647 vs parent $23453, but leftover hotspot moved to unassigned x=7 and day 8 still had 8 ripe. Binding everyone exclusive starves unassigned tiles.
- Same full columns plus x=7 given to actor 5 (10-tile NE home) plus skip-coop: seed 101 $23388 (below parent). A 10-tile exclusive harvest chain is 40 actions > 23 turns.
- BFS blobs grown from spawn/far corners: last shed-spawn actor got a disconnected scrap (diameter 8). Replaced with explicit columns.
## Next hypotheses
- Far-edge water-then-harvest: locked-spawn actors WATER every tile in their column before starting the 4-step harvest chain. After an 8-step morning walk they only have ~15 turns, enough to water 5 tiles but not to harvest-chain all 5 (seed 101 day 8 still left 6–7 far unwatered).
- Defer goose CARE (and egg HARVEST) on 25-ripe harvest days so the 5 greedy actors plus 4 far walkers finish watering; CARE still steals turns on the coop tiles.
- Skip hour-21 DROP while unwatered or ripe tiles remain: DROP_LATE_HOUR=21 can pull carriers to the shed for hours 21–23 and miss the last waters.
## Open questions
- After the 8-step walk to x=0, is stay-on-tile harvest the reason the far column still misses 1–2 tiles, or is CARE/DROP still stealing the last hours?
- Would assigning x=2/x=7 as *second* home tiles only for WATER (not exclusive harvest) cover the remaining leftovers without recreating n006 understaffing?
- Last plant day is 25; day 28 leftover ripe and last-day EOD shed wheat may still miss a SELL turn.
