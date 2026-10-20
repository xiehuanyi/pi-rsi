# Summary n003: Buy NE land and scale wheat

Bought NE land after first harvest and raised MAX_HANDS to 8, planting all unlocked wheat tiles with stay-on-tile labor. Official validation score 22268.97 (parent 16217), margin 18708.31, win_rate 1.0, 32/32 wins, errors 0. Worker quick-set rose from 15888.3 to 22343.1 (NE-only); NE+SW was worse on quick.

- official score: 22,269 (delta vs parent 6,052, vs best 6,052)
- verdict: improved
- commit: c23113bc
- claim check: consistent — Handoff validation 22269.0 / margin 18708.3 / win_rate 1.00 / errors 0 / std 235.6 / min 21767 / max 22483 / n=32 matches official 22268.97 / 18708.31 / 1.0 / 0 / 235.64 / 21767 / 22483 / 32 (rounding). Quick figures are self-reported and correctly separated from validation.

## Git log
```
c23113b Clarify policy docstring: NE land only, not SW
ab4e0c2 Buy NE land after first harvest and tend 50 wheat tiles with 8 hands.
```
```
agent.py         |  2 +-
 src/constants.py | 28 ++++++++++++++++++----
 src/policy.py    | 73 +++++++++++++++++++++++++++++++++++++++++++++-----------
 3 files changed, 84 insertions(+), 19 deletions(-)
```
