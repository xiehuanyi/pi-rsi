# Summary n002: CryoSleep-consistent spend imputation + rules

CryoSleep-consistent spend imputation, ZeroSpend/HasAnySpend flags, planet/destination/deck one-hots, and shallow HistGradientBoosting replaced the parent logistic baseline. Official validation score rose from 0.7717 to 0.81254 (n=1739, SEM 0.00936). Worker quick-set: 0.79655 vs untouched 0.76335; cryo+one-hots LR only 0.76910.

- official score: 0.8125 (delta vs parent 0.04083, vs best -0.00517)
- verdict: improved
- commit: acb8299a
- claim check: consistent — Handoff correctly reports validation as harness-only and does not invent an official score; official validation is 0.81254 vs parent 0.7717. Worker quick figures (baseline 0.76335, LR 0.76910, HGB 0.79655) match the progress log.

## Git log
```
acb8299 Use shallow histogram boosting on the cryo-imputed features.
c5b27c1 Implement CryoSleep-consistent spend imputation and planet/deck one-hots.
```
```
src/features.py | 115 ++++++++++++++++++++++++++++++++++++++++++++++++--------
 src/model.py    |  28 +++++++++++++-
 train.py        |  16 +++++---
 3 files changed, 136 insertions(+), 23 deletions(-)
```
