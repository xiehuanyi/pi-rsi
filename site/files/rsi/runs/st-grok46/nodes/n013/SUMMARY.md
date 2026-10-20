# Summary n013: F-deck leftover HomePlanet from spend mix

n013 fills leftover F-deck HomePlanet NA with a per-frame LogisticRegression on amenity mix (luxury share, room-service share, zero-spend), applied only where Deck==F after group fill and hard A/B/C/T/G map. Official validation score 0.81829 (n=1739) vs parent 0.8108 (+0.00749). Worker's own quick-set: 0.80760 vs parent quick 0.80718 (+0.00042). Last-name fill was ablated out after hurting quick.

- official score: 0.8183 (delta vs parent 0.00748, vs best -0.00057)
- verdict: improved
- commit: 15411ee9
- claim check: consistent — Handoff/progress quick scores (parent 0.80718; spend-mix 0.80760; last-name+mix 0.80660; last-name-only 0.80475) are internally consistent and correctly labeled as quick, not validation. Official harness validation is 0.81829 (n=1739), which the worker did not claim; they only speculated holdout would not recover.

## Git log
```
15411ee Fill leftover F-deck HomePlanet NA from amenity-mix classifier.
```
```
src/features.py | 17 +++++++++++---
 src/impute.py   | 72 ++++++++++++++++++++++++++++++++++++++++++++++++++++++++-
 2 files changed, 85 insertions(+), 4 deletions(-)
```
