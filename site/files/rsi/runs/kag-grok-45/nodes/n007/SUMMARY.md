# Summary n007: More hands after NE unlock

Raised hires after NE unlock (POST_LAND_HANDS=7, unlock-gated; BASE=6). Official validation score 36405.19 vs parent 36584 (−179). Win rate 1.0, 0 errors, n=32. Worker quick: 7 gave 38894.3 vs baseline 38707.5; 8–10 all worse on quick. Hypothesis refuted.

- official score: 36,405 (delta vs parent -178.5, vs best -486.6)
- verdict: worse
- commit: d987f950
- claim check: consistent — Handoff validation 36405.2 / margin 33065.9 / win_rate 1 / errors 0 / std 3068.9 / n=32 and git SHA match official metrics; claimed ~−178 vs parent 36583.7 aligns with harness parent 36584. Quick numbers are worker-only and labeled as such.

## Git log
```
d987f95 n007: finalize POST_LAND_HANDS=7; validation 36405
5575018 n007: POST_LAND_HANDS=7 after NE (best quick)
982c7c9 n007: raise hires after NE unlock (POST_LAND_HANDS)
```
```
agent.py        |  6 +++---
 src/farm_ops.py | 26 ++++++++++++++++++++++++--
 src/market.py   | 28 +++++++++++++++++++++++-----
 3 files changed, 50 insertions(+), 10 deletions(-)
```
