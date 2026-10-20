# Summary n011: Luxury vs essential spend and IsChild

Replaced five amenity log1p columns with LuxurySpend and EssentialSpend (log1p sums) plus IsChild; CryoSleep rules unchanged. Official validation accuracy 0.80679 (n=1739, sem=0.00947) vs parent 0.8125 (delta −0.00571). Worker quick-set: 0.80045 vs parent quick 0.79655 (+0.00390, below fold std).

- official score: 0.8068 (delta vs parent -0.00575, vs best -0.01207)
- verdict: no_change
- commit: 2d1615eb
- claim check: consistent — Handoff correctly reports only worker quick 0.80045 (+0.00390 vs parent quick 0.79655) and states validation was harness-only; progress log matches. Official validation is 0.80679 vs parent 0.8125—worker did not claim a conflicting validation score.

## Git log
```
2d1615e Replace five amenity logs with luxury/essential spend sums and IsChild.
```
```
src/features.py | 28 +++++++++++++++++++---------
 train.py        |  6 +++---
 2 files changed, 22 insertions(+), 12 deletions(-)
```
