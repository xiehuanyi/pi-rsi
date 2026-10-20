# Summary n005: Fertilize wheat bonus window

Shipped 2 spawn-tile geese for on-farm fertilizer: FERTILIZE ages 2–4 before WATER, feed reserve, DROP at 12. Official validation score 23597.91 vs parent 22269 (+1329), win_rate 1.0, 0 errors, n=32. Worker quick-set: 23286.6 vs untouched 22343.1.

- official score: 23,598 (delta vs parent 1,329, vs best 1,329)
- verdict: improved
- commit: d8bc5448
- claim check: consistent — Handoff validation 23597.9 / margin 19941.1 / win_rate 1.0 / errors 0 / std 556.7 / min 22665 / max 24469 / n=32 matches official 23597.91 and companions; git sha d8bc544 matches. Quick 23286.6 and untouched 22343.1 are correctly labeled worker quick-set, not official.

## Git log
```
d8bc544 Fertilize wheat ages 2-4 using 2 spawn-tile geese.
```
```
agent.py         |   2 +-
 src/animals.py   | 281 +++++++++++++++++++++++++++++++++++++++++++++++++++++++
 src/constants.py |  12 ++-
 src/grid.py      |   6 ++
 src/policy.py    | 128 ++++++++++++++++++++-----
 5 files changed, 403 insertions(+), 26 deletions(-)
```
