# Summary n006: Surname and cabin occupancy

Added per-frame LastNameSize and CabinOccupancy to LightGBM features. Official validation score 0.81656 (n=1739, sem=0.00928) vs parent 0.8137; |Δ|=0.00286 within noise. Worker's quick-set: 0.80417 vs untouched parent 0.80732 (Δ=−0.00315).

- official score: 0.8166 (delta vs parent 0.00287, vs best -0.00115)
- verdict: no_change
- commit: 214cf049
- claim check: consistent — Handoff quick scores (parent 0.80732 → both 0.80417; occupancy-only 0.80460; LastNameSize-only 0.80534) match the progress log. Official harness validation is 0.81656 vs parent 0.8137; the handoff did not claim an official validation score.

## Git log
```
214cf04 Add per-frame LastNameSize and CabinOccupancy to LightGBM features.
```
```
src/features.py | 28 ++++++++++++++++++++++++++++
 1 file changed, 28 insertions(+)
```
