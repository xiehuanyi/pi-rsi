# Summary n005: Ames extras + Edwards outliers

n005 added TotalBath, TotalPorchSF, QualGrLiv; dropped HasGarage/HasBsmt; dropped Edwards/cheap GrLivArea>4000 from train only. Worker quick-set: 0.12053→0.11818. Official validation RMSLE 0.14524 (n=293) vs parent 0.1389 — slightly worse but within the no_change band.

- official score: 0.1452 (delta vs parent -0.00635, vs best -0.00635)
- verdict: no_change
- commit: 5253670a
- claim check: consistent — Handoff/progress agree on worker quick-set 0.11818 vs parent quick 0.12053 and correctly state validation was harness-only; they claim no official n005 score. Official validation is 0.14524 (worse than parent 0.1389), matching the handoff’s warned holdout risk rather than contradicting a claimed number.

## Git log
```
5253670 Add Ames extras and drop Edwards cheap palaces from train.
```
```
src/features.py | 51 +++++++++++++++++++++++++++++++++++++++++++++++----
 train.py        |  5 +++--
 2 files changed, 50 insertions(+), 6 deletions(-)
```
