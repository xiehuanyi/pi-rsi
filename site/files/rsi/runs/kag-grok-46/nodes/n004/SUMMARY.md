# Summary n004: Fertilize wheat bonus window

Added 3 geese for daily free fertilizer plus eggs; FERTILIZE wheat ages 2–3 to hit yield 6. Skipped $100 bought fertilizer. Official validation score 20735.5 (parent 16217; +4518.5), margin 17165.53, win_rate 1.0, 32 games, 0 errors. Worker quick-set: 21822.08 vs untouched 15888.3.

- official score: 20,736 (delta vs parent 4,519, vs best -1,533)
- verdict: improved
- commit: 8123f990
- claim check: consistent — Handoff validation matches official metrics exactly (20735.5, margin 17165.53, win_rate 1.0, n=32, errors=0, std 1884.07, min 18325, max 24975). Parent cited as 16216.75 vs auditor baseline 16217 (rounding). Quick scores are worker-only and not contradicted.

## Git log
```
8123f99 Fertilize wheat in the ages 2-4 bonus window using 3 geese.
```
```
agent.py         |   2 +-
 src/constants.py |  10 ++
 src/grid.py      |  13 ++
 src/livestock.py | 146 ++++++++++++++++++++
 src/market.py    | 127 ++++++++++++++++++
 src/policy.py    | 395 ++++++++++++++++++++++++++++++++++---------------------
 6 files changed, 543 insertions(+), 150 deletions(-)
```
