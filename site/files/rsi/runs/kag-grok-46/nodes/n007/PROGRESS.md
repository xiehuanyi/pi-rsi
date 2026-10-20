# n007 PROGRESS

## Hypothesis
Defer goose CARE (and egg HARVEST) on days with many ripe wheat tiles, keeping FEED+COLLECT, so all 9 actors stay on the water→harvest→replant→water chain. Seed 101 still left 4–10 tiles unwatered at hour 23.

## Plan
1. Measure untouched n005 parent on quick.
2. Diagnose seed 101: CARE/egg HARVEST vs unwatered-at-23 on harvest days (is CARE the leftover, or DROP walks?).
3. Skip CARE + egg HARVEST while wheat labor remains (ripe / unwatered / plantable empties); keep FEED+COLLECT and coop walks for those. Harvest eggs at max_held=4 so production is not discarded.
4. Iterate threshold on quick, then validation.

## Baseline
Starting from parent n005 (official 23,598).
- untouched quick: score 23286.6; margin 19618.1; win_rate 1.00; errors 0; std 318.9; elapsed 8.2s
  Command: `eval/eval.py --seedset quick`
  Matches n005 worker quick. About to diagnose seed 101 CARE vs hour-23 leftovers.

## Diagnosis (untouched n005, seed 101 seat 0, money 23453)
Heavy harvest days leave 1–7 tiles unwatered at hour 23. CARE is 4/day and egg HARVEST is ~5/day even on those days (2 geese should need 2 CARE + 2 HARVEST; extras are DROP visitors standing on spawn coops). FEED stays at 2, COLLECT at 3.

Leftover days include 8 (unw23=6), 12 (7), 13 (5), 14 (4), 16 (7), 20 (6), 21 (6), 22 (4), 24 (7). CARE+egg HARVEST ≈ 9 actions/day, enough to close those waters if redirected.

## v1
Skip CARE and non-cap egg HARVEST while `wheat_chain_busy` (unwatered OR ripe OR plantable empty). Keep FEED, COLLECT_FERTILIZER, BUILD/PLACE, and drain eggs at max_held=4. Do not walk to coops for eggs while the chain is busy.

About to re-diagnose seed 101 and run quick.

## v1 result
- seed 101 seat0 **21693** (was 23453). Leftovers did not close (day 8/12/16/20 still 6–7 unwatered). CARE fell to 0 on most days including non-harvest mornings; FEED rose to 4–6 (double-FEED no-ops, same failure as n005 v4). Egg income dropped.
- quick: **score 21879.6** (was 23286.6); margin 18235.6; win_rate 1.00; errors 0; std 232.0
  Command: `eval/eval.py --seedset quick`

v1 was too broad: `wheat_chain_busy` is true every morning (nothing watered yet), so CARE never ran until the field was done — and harvest days never finished, so CARE never ran. DROP visitors on spawn coops issued extra FEED.

## v2
Defer CARE only on latched harvest-cohort days (`ripe>=8` or `ripe+replanted>=18`) AND while the wheat chain is busy. One unit per coop tile may FEED/COLLECT/CARE so DROP visitors fall through to DROP/wheat. Keep at-cap egg HARVEST.

About to diagnose seed 101 and run quick.

## v2 result
- seed 101 seat0 **18019**. Leftovers worse (day 13/17/21/25 unw23=11–13). CARE=0 from day 6–28. FEED/COLLECT correctly 2, but exclusive-owner blocked anyone-on-coop CARE: occupant COLLECTs fertilizer and leaves to FERTILIZE before CARE, and no visitor is allowed to CARE.
- quick: **score 17871.4** (was 23286.6); margin 14265.8; win_rate 1.00; errors 0; std 133.7
  Command: `eval/eval.py --seedset quick`

Exclusive-per-coop-tile is a dead end (same class as n005 assigned-only). Revert that; keep harvest-day latch.

## v3
Harvest-day defer only (ripe>=8 or ripe+replanted>=18) while wheat chain busy. Anyone-on-coop restored. Skip CARE + non-cap egg HARVEST; keep FEED+COLLECT and at-cap harvest. No exclusive owner.

## v3 result
- seed 101 seat0 **22713** (was 23453). Harvest-day CARE/eHARV dropped to 0 as intended (days 8, 12, 14). Leftovers did not close (day 8/12/16/20 still unw23=6–7). FEED rose to 4–6 on those days: DROP visitors carrying harvested wheat FEED the unfed goose instead of DROPping.
- quick: **score 22989.4** (was 23286.6); margin 19376.0; win_rate 1.00; errors 0; std 464.0
  Command: `eval/eval.py --seedset quick`

CARE skip itself does not free leftover waters; DROP-on-coop FEED no-ops eat the slack and egg income drops.

## v4
Same harvest-day defer, but DROP visitors (inventory >= 12 or wheat > 1) skip all coop actions so they DROP/return to wheat. Occupants still FEED+COLLECT.

## v4 result
- Identical to v3 (seed 101 22713, quick 22989.4). Extra FEED is 1-wheat shed pickups after DROP, not harvest loads, so wheat>1 skip was a no-op.

## v5
On harvest days, only the unit assigned to the coop (target==pos) may PICKUP wheat for FEED. DROP visitors skip that pickup.

## v5 result
- seed 101 seat0 **23011** (parent 23453, still slightly down). FEED back to 2 on harvest days. Some leftovers closed (day 9/17/21 unw23=0 vs parent 1/3/6); peak days still 5–7.
- quick: **score 23665.8** (was 23286.6); margin 20068.1; win_rate 1.00; errors 0; std 514.3; min 23011 max 24566; n=12
  Command: `eval/eval.py --seedset quick`

First positive result. Harvest-day CARE defer works only if DROP visitors cannot PICKUP wheat/FEED. Cleaning dead wheat>1 FEED branch, then commit and validation.

Committed. About to run validation.

## Validation (v5)
- validation: **score 24088.0** (parent 23597.9); margin 20525.8; win_rate 1.00; errors 0; std 765.3; min 23278 max 26443; n_games 32
  Command: `eval/eval.py --seedset validation`
- git: `db7d14ace4be13287f679d31db9edeec3b29b929`

Shipped harvest-day CARE/egg-HARVEST deferral with assigned-only feed pickup. Naive CARE skip (v1–v4) lost eggs and added FEED no-ops without closing leftovers.
