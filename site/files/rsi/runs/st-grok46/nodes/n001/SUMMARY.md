# Summary n001: Gradient boosting + cabin/group features

Switched from logistic regression to LightGBM with cabin deck/num/side, group id/size, categoricals, log1p spends, Age median, and CryoSleep-from-spend. Official validation score 0.81771 (n=1739) vs parent 0.7717 (+0.046). Worker quick-set: 0.80331 vs baseline quick 0.76335.

- official score: 0.8177 (delta vs parent 0.046, vs best 0.046)
- verdict: improved
- commit: b42f6f6b
- claim check: consistent — Handoff/progress claim quick 0.80331 (+0.03996 vs quick baseline 0.76335); they do not claim official validation. Official validation is 0.81771 vs parent 0.7717—aligned directionally and stronger than quick.

## Git log
```
b42f6f6 Replace logistic regression with LightGBM on cabin/group features.
```
```
src/features.py | 124 ++++++++++++++++++++++++++++++++++++++++++++++++++------
 src/model.py    |  42 ++++++++++++++-----
 train.py        |  13 +++---
 3 files changed, 149 insertions(+), 30 deletions(-)
```
