# Summary n003: CatBoost native categoricals with minimal FE

Swapped the 8-feature ridge for CatBoostRegressor with native categoricals (incl. MSSubClass), log1p/expm1 target, median/'Missing' fills, plus TotalSF and Age. Official validation RMSLE 0.14379 (n=293, sem=0.01654) vs parent 0.1836. Worker quick-set: 0.12187 vs ridge 0.16778. Absolute delta vs parent is 0.03981, inside the |δ|<0.05836 band.

- official score: 0.1438 (delta vs parent 0.0398, vs best -0.0049)
- verdict: no_change
- commit: 9f9b9835
- claim check: consistent — Handoff correctly reports validation as harness-only and does not invent an official score; its quick-set 0.12187 (vs ridge 0.16778) matches the progress log. Official validation is 0.14379 vs parent 0.1836.

## Git log
```
9f9b983 Replace ridge with CatBoost native categoricals and minimal FE.
```
```
src/features.py | 82 +++++++++++++++++++++++++++++++++++++++++++------
 src/model.py    | 95 ++++++++++++++++++++++++++++++++++++++++++++++++++-------
 train.py        | 16 +++++-----
 3 files changed, 165 insertions(+), 28 deletions(-)
```
