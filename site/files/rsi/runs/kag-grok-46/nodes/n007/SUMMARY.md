# Summary n007: Defer goose CARE on harvest days

Deferred goose CARE and egg HARVEST on latched wheat-harvest days (ripe≥8 or ripe+replant≥18) while the wheat chain is busy; kept FEED/COLLECT and assigned-only wheat pickup for feed. Official validation score 24087.97 vs parent 23598 (+490); margin 20525.81; win_rate 1.0; 32 games; 0 errors. Worker quick-set: 23665.8 (was 23286.6).

- official score: 24,088 (delta vs parent 490.1, vs best 490.1)
- verdict: improved
- commit: db7d14ac
- claim check: consistent — Handoff validation 24088.0 / margin 20525.8 / std 765.3 / min 23278 / max 26443 / n=32 / errors 0 match official 24087.97 / 20525.81 / 765.26 (rounding). Parent cited as 23597.9 vs harness 23598. Worker quick 23665.8 is self-reported only.

## Git log
```
db7d14a Defer goose CARE and egg harvest on wheat harvest days.
```
```
agent.py         |  3 +-
 src/animals.py   | 96 ++++++++++++++++++++++++++++++++++++++++++++++++++------
 src/constants.py |  5 +++
 src/policy.py    | 16 +++++++---
 4 files changed, 104 insertions(+), 16 deletions(-)
```
