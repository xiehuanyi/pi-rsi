# Summary n003: Buy NE land, extend hand farm

Added BUY_LAND for NE when money > 4000 and farmed all unlocked tiles (50) with TARGET_HANDS=6. Official validation score 8229.41 vs parent 9085 (delta −855.6). Same-crop carrot expansion glutted the market and cut revenue; tuning hands, thresholds, partitions, and plant caps never beat no-land.

- official score: 8,229 (delta vs parent -855.2, vs best -28,662)
- verdict: worse
- commit: 97ceabec
- claim check: consistent — Worker validation 8229.4 matches official 8229.41; cited parent 9084.6 aligns with harness parent 9085. Quick-set figures (baseline 11690.2, final 8656.7, sweeps) are labeled as quick and match the progress log; they are not the official validation score.

## Git log
```
97ceabe Restore index-mod partition; keep BUY_LAND NE at money>4000
575798e Buy NE land once money > 4000; farm already covers unlocked tiles
```
```
agent.py        |  5 ++---
 src/farm_ops.py |  2 ++
 src/market.py   | 43 ++++++++++++++++++++++++++++++++++++++-----
 3 files changed, 42 insertions(+), 8 deletions(-)
```
