# Summary n005: Buy NE land under melon tile cap

Added day≥10 BUY_LAND for NE ($1000) with MELON_MAX_TILES=16 and TARGET_HANDS=6; new tiles meant for carrots. Official validation score 36583.72 (margin 33230.41, win_rate 1.0, n=32, errors 0) vs parent 36892 — about −308. Worker quick-set peaked ~38867 with a money gate, but that variant also lost on validation. Labor left ~20–30 tiles empty.

- official score: 36,584 (delta vs parent -308.1, vs best -308.1)
- verdict: worse
- commit: ab628537
- claim check: consistent — Handoff validation 36583.7 / margin 33230.4 / win_rate 1.0 / errors 0 / std 2771.9 matches official 36583.72 / 33230.41 / 1.0 / 0 / 2771.91. Parent cited as 36891.8 aligns with auditor parent 36892; ~−308 regression claim is correct. Quick figures are explicitly labeled worker quick-set.

## Git log
```
ab62853 Prefer day-10 NE buy without money gate
303c324 Tune NE buy to post-melon-sale money gate
5c461c2 Buy NE land after day 10 under melon tile cap
```
```
agent.py        |  8 ++++----
 src/farm_ops.py |  9 +++++++++
 src/market.py   | 40 +++++++++++++++++++++++++++++++++++-----
 3 files changed, 48 insertions(+), 9 deletions(-)
```
