# Summary n002: Wide regularized linear model: ordinal + one-hot + log areas

Wide RidgeCV with ordinal quality maps, train-only one-hots (Neighborhood etc.), median impute, log1p areas, TotalSF/TotalBath. Official validation RMSLE 0.14224 (n=293, std 0.11043) vs parent 0.1836. Worker quick-set: 0.16778→0.13125. Alpha grid widened to 1–1000 after GCV hit 100.

- official score: 0.1422 (delta vs parent 0.04135, vs best -0.00044)
- verdict: no_change
- commit: 40a8222f
- claim check: consistent — Handoff/progress only claim worker quick-set scores (baseline 0.16778 → wide 0.13125) and parent official 0.18359; they did not claim an official validation score for n002. Official harness score is 0.14224, which is consistent with a real improvement vs parent and with not overstating validation results.

## Git log
```
40a8222 Wide ridge on ordinal maps, train-only one-hots, and log areas.
```
```
src/features.py | 190 +++++++++++++++++++++++++++++++++++++++++++++++++++++---
 src/model.py    |  16 +++--
 train.py        |  12 ++--
 3 files changed, 199 insertions(+), 19 deletions(-)
```
