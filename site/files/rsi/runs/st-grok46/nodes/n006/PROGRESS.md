# n006 progress

## Plan
Hypothesis: add per-frame LastNameSize (surname frequency) and CabinOccupancy (count sharing imputed Cabin; 1 if cabin NA). Keep LightGBM and current features. Count only inside the current frame.

## 2026-09-10 start
- Worktree is parent n004 (commit 8b05a0e): group-consistent imputation + LightGBM.
- Name is always two tokens ("First Last"); 160 missing. Last names span multiple groups (1388/2090), corr(LastNameSize, GroupSize)=0.35 so not a duplicate of GroupSize.
- Cabin occupancy corr with GroupSize=0.87 (more redundant). Solo cabins transported ~0.45 vs occupancy 2–4 ~0.59–0.61.
- About to run untouched quick as the starting point.

## Untouched parent quick (before edits)
Command: eval/eval.py --seedset quick with the task venv python.
Result: score **0.80732** (folds [0.79702, 0.81232, 0.81988, 0.80638, 0.80101], score_std=0.00812, score_sem=0.00363, n=6954, elapsed=11.3s). Matches n004.

## Implementation
- `src/features.py`: `last_name`, `last_name_size`, `cabin_occupancy`. Added LastNameSize and CabinOccupancy to NUM_FEATURES.
- Per-frame only via `_raw`. Missing Name → LastNameSize 0; missing Cabin after group fill → CabinOccupancy 1.
- Sanity: 160 names → size 0; Cabin NA 164→91 after fill; shared last "Slable" is 5 in train / 3 in predict (no concat leak).

## Hypothesis eval (both features)
About to run quick after LastNameSize + CabinOccupancy.

Result: score **0.80417** (folds [0.79063, 0.81375, 0.81484, 0.80638, 0.79522], elapsed=11.5s).
Delta vs untouched: **−0.00315**. Fold deltas: −0.00639, +0.00143, −0.00504, 0, −0.00579 (three down, one up, one tied). Below fold std (~0.008) and not a consistent lift — hypothesis not supported on quick.

## Ablations
Next: occupancy-only and lastname-only on the same quick seed set, without shipping a different hypothesis.

Occupancy-only quick: **0.80460** (folds [0.79347, 0.80516, 0.81844, 0.80566, 0.80029], std=0.00819). All five folds down vs parent (deltas −0.00355, −0.00716, −0.00144, −0.00072, −0.00072).

LastNameSize-only quick: **0.80534** (folds [0.78424, 0.8159, 0.82277, 0.80566, 0.79812], std=0.01351). Fold 0 dropped −0.01278; std jumped vs parent 0.00812. Earth surname collisions.

Restored both features (hypothesized change) as the shipped commit `214cf049774b6c60604d0bd2b46cae687ada7702`. Did not switch hypotheses.

## Diagnostics (not scores)
- Cabins never span groups (0 of 5254). Occupancy > GroupSize never happens; occupancy < GroupSize on 1001 split-cabin rows. corr(CabinOccupancy, GroupSize)=0.87.
- 1388/2090 last names span >1 group; corr(LastNameSize, GroupSize)=0.35.
- Sharing a last name *inside a group* is a better family definition: 2752 rows, transported 0.551 vs 0.464 otherwise.

## Stop
Quick does not support the hypothesis. Writing HANDOFF and proposals. No more evals.
