# Summary n007: Within-group family flag

Replaced LastNameSize/CabinOccupancy with within-group FamilyInGroup. Official validation score 0.81484 (n=1739) vs parent 0.8166 (Δ −0.00176). Worker's quick-set: FamilyInGroup 0.80603 vs parent 0.80417 (+0.00186); dropping FamilyInGroup scored worker's quick 0.80732.

- official score: 0.8148 (delta vs parent -0.00172, vs best -0.00287)
- verdict: no_change
- commit: fb23dd29
- claim check: consistent — Handoff/progress quick scores agree (parent 0.80417, FamilyInGroup 0.80603, ablation 0.80732). No false official claim; harness validation 0.81484 is flat vs parent 0.8166, matching the worker's noise caveat.

## Git log
```
fb23dd2 Replace global surname/cabin counts with within-group FamilyInGroup.
```
```
src/features.py | 31 ++++++++++++++-----------------
 1 file changed, 14 insertions(+), 17 deletions(-)
```
