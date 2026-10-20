# Summary n014: Group-consistent missing imputation

Added per-frame unique group fill for HomePlanet/Cabin/Destination plus hard deck→planet, then recomputed CabinOccupancy after Cabin fill. Official validation score 0.81484 (n=1739, sem=0.00931) vs parent 0.8097 (Δ=+0.00514, within no_change). Worker quick-set: 0.80460 vs parent quick 0.80818 (Δ=−0.00358; 4/5 folds down).

- official score: 0.8148 (delta vs parent 0.00518, vs best -0.00402)
- verdict: no_change
- commit: 8fcf5bdc
- claim check: consistent — Handoff correctly labels all reported scores as quick-set (0.80460 shipped, parent 0.80818, ablations matching the progress log) and does not claim an official validation number. Official harness score is 0.81484; no contradiction with the handoff’s quick-set claims.

## Git log
```
8fcf5bd Fill group-shared location fields; recompute cabin occupancy after fill.
```
```
src/features.py | 61 +++++++++++++++++++++++++++++++++++++++++++++-------
 src/impute.py   | 66 +++++++++++++++++++++++++++++++++++++++++++++++++++++++++
 2 files changed, 119 insertions(+), 8 deletions(-)
```
