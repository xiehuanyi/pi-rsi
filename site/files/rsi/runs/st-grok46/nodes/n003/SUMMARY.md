# Summary n003: Group-level transported prior features

n003 added group structure features (GroupSize, IsAlone, SameCabinAsGroup, LOO group transported priors, group HomePlanet/Cabin fill), LightGBM, and predict-batch group-proba blend. Official validation score 0.80161 (n=1739, sem 0.00956) vs parent 0.7717 (+0.02991). Worker quick-set: 0.80073 vs starter 0.76335.

- official score: 0.8016 (delta vs parent 0.0299, vs best -0.0161)
- verdict: improved
- commit: 8c816efa
- claim check: consistent — Handoff and progress log both report quick-set 0.80073 (starter 0.76335) and state validation was not run in-node; they do not misstate the harness score. Official validation is 0.80161 vs parent 0.7717. Quick and validation are different seed sets, so the claimed 0.80073 is not the official metric.

## Git log
```
8c816ef Allow ablating leave-one-out group target columns.
6e45b3e Add group structure, LOO transported priors, and group-fill features.
```
```
src/features.py | 176 +++++++++++++++++++++++++++++++++++++++++++++++++++-----
 src/group.py    | 103 +++++++++++++++++++++++++++++++++
 src/model.py    |  45 +++++++++++----
 train.py        |  17 +++---
 4 files changed, 310 insertions(+), 31 deletions(-)
```
