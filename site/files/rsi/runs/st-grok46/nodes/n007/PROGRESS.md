# n007 progress

## Plan
Hypothesis: within-group family flag (FamilyInGroup). Count how many passengers in the same PassengerId group (gggg) share this passenger's last name (0 if Name missing; 1 = no same-name mate). Do not use global LastNameSize or CabinOccupancy. Keep LightGBM and the rest of the current feature set.

## Starting point
Reading docs/, train.py, src/features.py (parent n006 still has LastNameSize + CabinOccupancy). Next: measure untouched parent quick score, then replace those two counts with FamilyInGroup.

## 2026-09-10 — untouched parent quick
About to run evaluator on the n006 snapshot (commit 214cf04, LastNameSize + CabinOccupancy still in NUM_FEATURES) so the later FamilyInGroup delta is against a number from this worktree, not memory.

Command:
`~/pi-rsi/pi_rsi/tasks/kaggle-spaceship-titanic/.venv/bin/python eval/eval.py --seedset quick --python ~/pi-rsi/pi_rsi/tasks/kaggle-spaceship-titanic/.venv/bin/python`

Untouched parent (n006 snapshot, LastNameSize + CabinOccupancy): **quick score 0.80417** (folds [0.79063, 0.81375, 0.81484, 0.80638, 0.79522], score_std=0.00974, score_sem=0.00435, n=6954, elapsed=11.2s). Matches n006 handoff.

On `data/train.csv` FamilyInGroup (count of same last name in gggg; 0 if Name missing): 2752 rows with count>1, transported 0.55087 vs 0.46359 otherwise. corr vs GroupSize = 0.830. Residual vs GroupSize: 263 rows with GroupSize>1 and FamilyInGroup==1 (unrelated surnames in the group), 79 with GroupSize>1 and missing Name. Confirms the hypothesized signal and the GroupSize-correlation risk.

## 2026-09-10 — implement FamilyInGroup
Replace LastNameSize and CabinOccupancy with FamilyInGroup in `src/features.py`. Counts are per (group, last name) inside the current frame only; missing Name → 0. Keep LightGBM hyperparameters unchanged.

Commit: `fb23dd292259c5f4348e982f4aed26f03180a022`. Sanity-check: 2752 rows with FamilyInGroup>1, 160 zeros matching missing Name, FeatureBuilder no longer emits LastNameSize/CabinOccupancy.

## 2026-09-10 — FamilyInGroup quick eval
About to run the same quick seed set on the FamilyInGroup model.

FamilyInGroup (replacing LastNameSize + CabinOccupancy): **quick score 0.80603** (folds [0.79702, 0.8116, 0.80908, 0.80928, 0.80318], score_std=0.0053, score_sem=0.00237, n=6954, elapsed=11.2s).

Vs this node's untouched parent 0.80417: **Δ +0.00186**. Fold deltas: +0.00639, −0.00215, −0.00576, +0.00290, +0.00796 (three up, two down). Below fold std and folds do not move together.

Vs n006-reported n004 quick 0.80732 (no surname/occupancy counts): **Δ −0.00129**. Fold 2 is −0.01080 vs that snapshot.

LightGBM split counts on full `data/train.csv`: FamilyInGroup 363 (rank 12), GroupSize 424. corr(FamilyInGroup, GroupSize)=0.830; FamilyInGroup equals GroupSize on 84.9% of rows. Trees do use it a little, but it is nearly a GroupSize duplicate.

## 2026-09-10 — ablation: drop FamilyInGroup (n004-like, not shipped)
Temporarily remove FamilyInGroup and re-run quick so the family-count delta is isolated from "just dropping n006's two counts". Restore `src/features.py` after.

Ablation (FamilyInGroup dropped, not shipped): **quick score 0.80732** (folds [0.79702, 0.81232, 0.81988, 0.80638, 0.80101], n=6954, elapsed=10.8s). Matches n006's n004 snapshot. FamilyInGroup vs this ablation: **Δ −0.00129**. Fold deltas: 0, −0.00072, −0.01080, +0.00290, +0.00217. Fold 2 dropped; not a consistent lift.

Restored committed FamilyInGroup code (`fb23dd292259c5f4348e982f4aed26f03180a022`). Worktree clean. metrics.quick.json remains the shipped FamilyInGroup run (0.80603).

Conclusion: the within-group family *count* is real but redundant with GroupSize (equal on 84.9% of rows). Do not stack more surname/group-size integers. Ship the hypothesized feature; treat the +0.00186 vs n006 as noise (and mostly the removal of LastNameSize/CabinOccupancy).

## 2026-09-10 — handoff
Wrote HANDOFF.md and proposals.json. Re-ran shipped FamilyInGroup code: quick **0.80603** again (same folds). Final commit `fb23dd292259c5f4348e982f4aed26f03180a022`. Node complete.
