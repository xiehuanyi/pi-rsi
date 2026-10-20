# Summary n006: Compact spawn-aware 5x10 regions

Shipped spawn-aware locked-column matching for SW/SE shed hands (no SW buy), replacing unconstrained greedy for those actors. Official validation score 21683.06 vs parent 22269 (−586); win_rate 1.0, 32 games, 0 errors. Worker quick-set also fell (21815.2 vs 22343.1). Exclusive rows/blocks and soft side penalties all scored worse on seed 101.

- official score: 21,683 (delta vs parent -585.9, vs best -1,915)
- verdict: worse
- commit: 967d3d19
- claim check: consistent — Handoff validation 21683.1 matches official 21683.06; git sha, win_rate, n_games, errors, and std align. Quick-set figures are labeled as such and not contradicted by harness.

## Git log
```
967d3d1 Spawn-aware strips for locked SW/SE hands.
```
```
agent.py         |  2 +-
 src/constants.py | 17 +++++-------
 src/grid.py      | 41 +++++++++++++++++------------
 src/policy.py    | 78 ++++++++++++++++++++++++++++++++++++++++++++------------
 4 files changed, 94 insertions(+), 44 deletions(-)
```
