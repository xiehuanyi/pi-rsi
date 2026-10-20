# Summary n001: LightGBM on full tabular features with ordinal/NA handling

Replaced 8-feature ridge with LightGBM on 84 tabular features (ordinal maps, train medians, UNK label cats, TotalSF/Age/RemodAge). Official validation RMSLE 0.1418 (n=293, std 0.1107, sem 0.014) vs parent 0.1836; |Δ|=0.0418 below the 0.05564 bar. Worker quick-set: 0.12694 vs ridge quick 0.16778.

- official score: 0.1418 (delta vs parent 0.04179, vs best 0.04179)
- verdict: no_change
- commit: 7549b29c
- claim check: consistent — Handoff correctly left official validation to the harness and only claimed worker quick-set 0.12694 (vs ridge quick 0.16778). Official score is 0.1418; parent cited as 0.18359 matches the 0.1836 baseline within rounding. No conflicting official numbers.

## Git log
```
7549b29 Replace 8-feature ridge with LightGBM on full tabular features.
```
```
src/features.py | 140 ++++++++++++++++++++++++++++++++++++++++++++++++++++----
 src/model.py    |  59 +++++++++++++++++++-----
 train.py        |  17 +++----
 3 files changed, 189 insertions(+), 27 deletions(-)
```
