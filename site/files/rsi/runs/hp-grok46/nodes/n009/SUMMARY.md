# Summary n009: OOF-tuned 4-member weights

Replaced equal 1/4 log blend with inner 5-fold OOF NNLS simplex weights (LGBM/XGB/CatBoost/Ridge). Official validation RMSLE 0.13676 (n=293) vs parent 0.1369 (Δ −0.00014). Worker quick: 0.12070 vs parent quick 0.11896 (worse, mainly fold 4).

- official score: 0.1368 (delta vs parent 0.00014, vs best 0.00014)
- verdict: no_change
- commit: 27f73180
- claim check: consistent — Handoff correctly left validation to the harness and did not invent an official score. Official 0.13676 matches the claimed parent 0.1369 within noise. Quick 0.12070 / parent-quick 0.11896 and fold diagnostics match the progress log; those are worker quick-set numbers, not official.

## Git log
```
27f7318 Replace equal 1/4 blend with OOF NNLS log-space weights.
```
```
src/model.py | 156 ++++++++++++++++++++++++++++++++++++++++++++++++-----------
 train.py     |   4 +-
 2 files changed, 130 insertions(+), 30 deletions(-)
```
