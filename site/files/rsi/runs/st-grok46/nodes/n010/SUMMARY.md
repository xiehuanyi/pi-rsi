# Summary n010: Group size, cabin side, within-group sharing

Added group size, cabin side, and within-group sharing features on cryo-imputed spends + depth-3 HGB. Official validation score 0.80794 (n=1739, SEM 0.00945) vs parent 0.8125 (Δ −0.00456). Worker quick-set rose 0.79655 → 0.80449 (+0.00794); that lift did not hold on the official seed set.

- official score: 0.8079 (delta vs parent -0.0046, vs best -0.01092)
- verdict: no_change
- commit: 16b80ec3
- claim check: consistent — Handoff correctly states validation was harness-only and does not claim an official n010 validation score. Worker quick 0.80449 (+0.00794 vs parent quick 0.79655) matches the progress log. Official harness score is 0.80794 vs parent 0.8125 — a small drop within the no_change band, contrary to the quick-set improvement narrative.

## Git log
```
16b80ec Add group size, cabin side, and within-group sharing features.
```
```
src/features.py | 77 ++++++++++++++++++++++++++++++++++++++++++++++++++++++---
 train.py        |  8 +++---
 2 files changed, 77 insertions(+), 8 deletions(-)
```
