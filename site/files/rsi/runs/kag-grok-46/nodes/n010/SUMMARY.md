# Summary n010: Fertilize wheat bonus window

Added 2 shed-adjacent geese for on-farm fertilizer, FERTILIZE-before-WATER on wheat ages 2–4, forced morning fertilizer PICKUP, and DROP only when idle or hour≥21 with no WATER jobs left. Official validation score 24574.56 vs parent 21683 (+2892), margin 20902.47, win_rate 1.0, 32 games, errors 0. Worker's own quick-set rose from 21815.2 to 24122.6.

- official score: 24,575 (delta vs parent 2,892, vs best -39.03)
- verdict: improved
- commit: 51fa3211
- claim check: consistent — Handoff validation 24574.6 / margin 20902.5 / std 714.3 / min–max 23449–26182 / win_rate 1.0 / 32 games / errors 0 matches official 24574.56, 20902.47, 714.34, 23449–26182 within rounding; git_sha 51fa321 matches.

## Git log
```
51fa321 Fertilize wheat ages 2-4 with 2 shed geese.
```
```
agent.py         |   3 +-
 src/animals.py   | 288 +++++++++++++++++++++++++++++++++++++++++++++++++++++++
 src/constants.py |  29 ++++--
 src/grid.py      |  47 +++++----
 src/policy.py    | 210 ++++++++++++++++++++++++----------------
 5 files changed, 461 insertions(+), 116 deletions(-)
```
