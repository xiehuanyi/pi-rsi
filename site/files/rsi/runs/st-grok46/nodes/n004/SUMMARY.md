# Summary n004: Group-consistent missing imputation

Added per-frame unique group-mate fill for HomePlanet/Cabin/Destination plus hard deck→planet map (A/B/C/T→Europa, G→Earth) in LightGBM features. Official validation score 0.81369 (n=1739, sem=0.00934) vs parent 0.8177 (Δ−0.00401). Worker's quick-set: 0.80331→0.80732.

- official score: 0.8137 (delta vs parent -0.00402, vs best -0.00402)
- verdict: no_change
- commit: 8b05a0e0
- claim check: consistent — Handoff/progress quick scores match (parent 0.80331, shipped 0.80732, no-Destination ablation 0.80674). Handoff did not claim an official validation win; harness score is 0.81369 vs parent 0.8177 (slightly down, within |Δ|<0.00853).

## Git log
```
8b05a0e Fill HomePlanet/Cabin/Destination from unique group-mates per frame.
```
```
src/features.py | 21 +++++++++++++++++--
 src/impute.py   | 64 +++++++++++++++++++++++++++++++++++++++++++++++++++++++++
 2 files changed, 83 insertions(+), 2 deletions(-)
```
