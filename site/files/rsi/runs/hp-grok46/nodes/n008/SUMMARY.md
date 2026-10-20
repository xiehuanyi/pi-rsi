# Summary n008: Robustify Ridge areas / Edwards

Ridge-only change: train-99th caps on GrLivArea/TotalBsmtSF/1stFlrSF/TotalSF with BsmtFinSF1 clipped to the TotalBsmtSF cap, plus Ridge-fit drop of Edwards/cheap GrLivArea>4000; trees and equal 1/4 blend unchanged. Official validation RMSLE 0.13578 vs parent 0.1369 (Δ −0.00112). Worker quick-set 0.11638 vs parent quick 0.11896.

- official score: 0.1358 (delta vs parent 0.00112, vs best 0.00098)
- verdict: no_change
- commit: 30dc1642
- claim check: consistent — Handoff correctly reports validation as harness-only and parent official 0.1369; official this node is 0.13578. Quick scores (0.11638 vs 0.11896) are self-reported and match the progress log; they are not the official metric.

## Git log
```
30dc164 Robustify Ridge with train-99th area caps and palace-row drop.
```
```
src/linear_features.py | 80 +++++++++++++++++++++++++++++++++++++++++++-------
 src/model.py           | 18 ++++++++++--
 train.py               |  8 +++--
 3 files changed, 91 insertions(+), 15 deletions(-)
```
