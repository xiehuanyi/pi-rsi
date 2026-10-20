# Summary n012: Ablate integer GroupId

n012 dropped integer GroupId from NUM_FEATURES (kept GroupSize and fills). Official validation score 0.81541 (n=1739, sem=0.0093) vs parent 0.8108, Δ +0.00461. Worker quick-set: 0.80761 vs untouched 0.80718 (Δ +0.00043). Flat on both; ablation alone does not clear the no_change band.

- official score: 0.8154 (delta vs parent 0.0046, vs best -0.00345)
- verdict: no_change
- commit: 742b6bbb
- claim check: consistent — Handoff quick scores (0.80761 vs 0.80718, Δ +0.00043) match the progress log. Worker correctly stated official validation was not run in-session; harness later reports 0.81541 vs parent 0.8108.

## Git log
```
742b6bb Drop integer GroupId from LightGBM features.
```
```
src/features.py | 4 ++--
 1 file changed, 2 insertions(+), 2 deletions(-)
```
