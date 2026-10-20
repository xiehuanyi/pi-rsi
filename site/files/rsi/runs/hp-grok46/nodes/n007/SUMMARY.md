# Summary n007: Bath/porch/QualArea features and Edwards outliers

Added TotalBath, TotalPorchSF, QualArea; dropped HasGarage/HasBsmt; dropped train rows with GrLivArea>4000 and SalePrice<300000. Official validation RMSLE 0.14766 (n=293, sem=0.01708) vs parent 0.1418 (|Δ|=0.00586, within noise). Worker quick-set: 0.12460 vs parent quick 0.12694 (−0.00234).

- official score: 0.1477 (delta vs parent -0.00586, vs best -0.01076)
- verdict: no_change
- commit: 8ee1ac42
- claim check: consistent — Handoff correctly did not claim an official validation score and reported only quick-set 0.12460 vs parent quick 0.12694. Harness official is 0.14766 (worse than parent 0.1418 by 0.00586). Quick numbers and fold story match the progress log.

## Git log
```
8ee1ac4 Add TotalBath/TotalPorchSF/QualArea and drop cheap Edwards palaces from train.
```
```
src/features.py | 45 +++++++++++++++++++++++++++++++++++++++++----
 train.py        |  7 ++++---
 2 files changed, 45 insertions(+), 7 deletions(-)
```
