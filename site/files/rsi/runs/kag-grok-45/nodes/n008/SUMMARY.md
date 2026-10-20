# Summary n008: Quadrant-local hand partition

Quadrant-local row-band ownership after NE unlock (NW_UNIT_COUNT=3, TARGET_HANDS=6, melon cap 16) raised official validation score to 37329.44 from parent 36584 (+745), win_rate 1.0, 0 errors, n=32. Contiguous bands beat within-quad modulo; NW=2 was stronger on worker quick (39528.8) but weaker on validation (37039.4).

- official score: 37,329 (delta vs parent 745.7, vs best 437.6)
- verdict: improved
- commit: ab07b2cc
- claim check: consistent — Handoff validation 37329.4 / margin 34021.3 / win_rate 1.0 / errors 0 / std 2579.6 / n=32 and git ab07b2cc match official metrics; claimed +745.7 vs parent ~36584 aligns. Quick figures are correctly labeled as worker evals.

## Git log
```
ab07b2c n008: polish comments; finalize NW=3 quadrant partition
4bbeda4 n008: prefer NW=3 on validation (hypothesis split)
2469631 n008: NW=2 row-band quadrant partition (best quick)
00c9d2d n008: quadrant-local hand partition after NE unlock
```
```
agent.py        |   6 +--
 src/farm_ops.py | 124 ++++++++++++++++++++++++++++++++++++++++++++++++++++----
 2 files changed, 119 insertions(+), 11 deletions(-)
```
