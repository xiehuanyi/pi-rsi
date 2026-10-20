# Summary n001: Multi-tile wheat farm with daily water/harvest route

Replaced the single-tile carrot loop with an 8-tile NW wheat farm (daily WATER, harvest at age 4, 2 new plants/day, sell every turn). Official validation score 9524.62 vs parent 3587 (margin 5975.19, win_rate 1.0, n=32, errors=0; min 7338 max 10439). Worker quick-set: 9360.67. Solo farmer cannot sustain the hypothesized 20+ daily-watered tiles.

- official score: 9,525 (delta vs parent 5,938, vs best -6,692)
- verdict: improved
- commit: 7ef83541
- claim check: consistent — Handoff validation score 9524.62, margin 5975.19, win_rate 1.00, errors 0, std 804.27, min 7338, max 10439 match official harness metrics exactly; quick 9360.67 is correctly labeled as a worker quick-set result and matches the progress log.

## Git log
```
7ef8354 Replace carrot loop with 8-tile NW wheat farm.
```
```
agent.py     |  33 ++-------
 src/wheat.py | 238 +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
 2 files changed, 243 insertions(+), 28 deletions(-)
```
