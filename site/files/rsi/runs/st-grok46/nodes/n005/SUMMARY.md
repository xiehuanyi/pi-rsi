# Summary n005: Surname and cabin occupancy counts

Added per-frame CabinOccupancy (dropped SurnameFreq after ablation). Worker quick-set: cabin-only 0.80818 vs parent quick 0.80331 (+0.00487). Official validation score 0.80966 (n=1739, sem=0.00941) vs parent 0.8177 (Δ=-0.00804), within no_change band.

- official score: 0.8097 (delta vs parent -0.00805, vs best -0.00805)
- verdict: no_change
- commit: c8445144
- claim check: consistent — Handoff/progress claim only quick-set cabin-only 0.80818 and correctly flag official as separate; harness validation score is 0.80966, not claimed as improved vs parent 0.8177.

## Git log
```
c844514 Keep cabin occupancy; drop global surname frequency.
23c7acd Add per-frame surname frequency and cabin occupancy counts.
```
```
src/features.py | 12 ++++++++++++
 1 file changed, 12 insertions(+)
```
