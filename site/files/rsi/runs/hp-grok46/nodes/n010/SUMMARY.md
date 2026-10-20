# Summary n010: Cap Ames area outliers for linear model

Added transform-time area caps on the n002 WideLinear+Ridge pipeline (global living 4000 backstop plus tighter Edwards/Partial p99 including BsmtFinSF1/LotFrontage); no cheap-palace train drop. Official validation RMSLE 0.13674 vs parent 0.1422 (Δ=-0.00546). Worker quick-set: 0.11993 vs parent 0.13125, with fold 4 0.17596→0.13931.

- official score: 0.1367 (delta vs parent 0.0055, vs best -0.00096)
- verdict: no_change
- commit: ae9335be
- claim check: consistent — Handoff quick-set scores (parent 0.13125 → 0.11993, fold 4 0.17596→0.13931) match the progress log and are labeled as quick, not official. Official validation is 0.13674 vs parent 0.1422 (Δ=-0.00546), a smaller gain than the quick-set story and below the 0.0462 no_change threshold; the handoff did not claim an official validation number.

## Git log
```
ae9335b Cap Ames area outliers at transform time for the linear model.
```
```
src/features.py | 118 ++++++++++++++++++++++++++++++++++++++++++++++++++------
 train.py        |   3 +-
 2 files changed, 108 insertions(+), 13 deletions(-)
```
