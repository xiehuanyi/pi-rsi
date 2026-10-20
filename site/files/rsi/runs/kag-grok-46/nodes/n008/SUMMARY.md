# Summary n008: Compact spawn-aware NW+NE regions

Assigned locked SW/SE spawns compact exclusive far-edge columns (x=0,1,8,9), preferred NORTH off locked tiles, and skipped coop CARE/FEED for those walkers; shed-spawn actors stayed greedy. Official validation score 24613.59 vs parent 23598 (+~1016); win_rate 1.0, errors 0, n_games 32. Worker quick-set: 24974.6 vs 23286.6.

- official score: 24,614 (delta vs parent 1,016, vs best 525.6)
- verdict: improved
- commit: ee850653
- claim check: consistent — Handoff validation 24613.6 / margin 21015.7 / win_rate 1.00 / errors 0 / std 752.0 / min 23519 / max 25798 / n_games 32 matches official 24613.59, 21015.66, 1.0, 0, 752.02, 23519, 25798, 32. Parent cited as 23597.9 ≈ auditor parent 23598. Quick and seed-101 figures are labeled worker-only and not contradicted by the log.

## Git log
```
ee85065 Clarify home_regions docstring: only locked-spawn columns are exclusive.
c41146a Assign locked SW/SE spawns compact far-edge columns.
```
```
agent.py         |   2 +-
 src/constants.py |  10 ++++++
 src/grid.py      | 102 +++++++++++++++++++++++++++++++++++++++++++++++++++----
 src/policy.py    |  40 ++++++++++++++--------
 4 files changed, 132 insertions(+), 22 deletions(-)
```
