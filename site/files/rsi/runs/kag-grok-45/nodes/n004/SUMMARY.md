# Summary n004: Parallel melon (or melon+carrot) loop

Switched the parallel hired-hand farm to melon primary with harvest at age 10, capped at 16 live melon tiles and a price≥180 plant/buy gate that falls back to carrot. Official validation score 36891.84 (margin 33510.31, win_rate 1.0, n=32, errors 0) vs parent 9085 (~+27.8k). Worker quick peaked at 37637.3 under the same knobs.

- official score: 36,892 (delta vs parent 27,807, vs best 27,807)
- verdict: improved
- commit: e6efa200
- claim check: consistent — Handoff validation 36891.8 / margin 33510.3 / win_rate 1.00 / errors 0 / std 2092.9 / n=32 matches official 36891.84 / 33510.31 / 1.0 / 0 / 2092.88 / 32; git sha matches. Parent 9084.6 aligns with given 9085. Quick figures are labeled worker-only and match the progress log.

## Git log
```
e6efa20 n004: cap melon at 16 tiles, price gate 180 for carrot mix
fdd45b2 n004: parallel melon loop with carrot fallback on price crash
```
```
agent.py        |  18 ++++---
 src/farm_ops.py | 143 ++++++++++++++++++++++++++++++++++++++++----------------
 src/market.py   |  64 +++++++++++++++++++------
 3 files changed, 167 insertions(+), 58 deletions(-)
```
