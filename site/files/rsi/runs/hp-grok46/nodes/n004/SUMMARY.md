# Summary n004: LGBM+XGB+CatBoost log-space blend

Equal-weight LGBM+XGB+CatBoost log-space blend on unchanged TabularFeatures. Official validation RMSLE 0.13889 vs parent 0.1418 (Δ=−0.00291). Worker quick-set: 0.12053 vs parent quick 0.12694 (all five folds down; hard fold barely moved).

- official score: 0.1389 (delta vs parent 0.00291, vs best 0.00291)
- verdict: no_change
- commit: 97778e94
- claim check: consistent — Handoff correctly left validation to the harness and only reported worker quick 0.12053 / parent quick 0.12694 (matches progress log). Official score is 0.13889; worker did not invent a validation number for this node.

## Git log
```
97778e9 Blend LGBM, XGB, and CatBoost in log space.
```
```
src/model.py | 72 ++++++++++++++++++++++++++++++++++++++++++++++++++----------
 train.py     |  7 +++---
 2 files changed, 64 insertions(+), 15 deletions(-)
```
