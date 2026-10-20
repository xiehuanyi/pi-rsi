# Handoff n007: Within-group family flag
## Hypothesis
Do not use global LastNameSize (n006: noisy, Earth collisions). Parse last name from Name and, within each frame, add FamilyInGroup = count of passengers in the same PassengerId group (gggg) who share that last name (0 if Name missing; 1 means traveling without a same-name mate). Keep LightGBM; do not add CabinOccupancy or global surname frequency.
## What I did
- Left the CLI contract in `train.py` and LightGBM hyperparameters in `src/model.py` unchanged.
- In `src/features.py`: replaced `LastNameSize` and `CabinOccupancy` with `family_in_group` / `FamilyInGroup`. Last name is the last whitespace token of Name. The count is per (group, last name) inside the current frame only; missing Name → 0.
- Counts are never taken on a train+predict concat. `_raw` still transforms each frame on its own.
- Did not modify `eval/` or `docs/`.
- Ablated FamilyInGroup off (n004-like features) on the same quick seed set; not shipped.
## Result
- Untouched parent (n006 snapshot, LastNameSize + CabinOccupancy) quick: score **0.80417** (folds [0.79063, 0.81375, 0.81484, 0.80638, 0.79522], score_std=0.00974, score_sem=0.00435, n=6954, elapsed=11.2s).
- FamilyInGroup (replacing those two counts) quick: score **0.80603** (folds [0.79702, 0.8116, 0.80908, 0.80928, 0.80318], score_std=0.0053, score_sem=0.00237, n=6954, elapsed=11.2s).
- Command: `~/pi-rsi/pi_rsi/tasks/kaggle-spaceship-titanic/.venv/bin/python eval/eval.py --seedset quick --python ~/pi-rsi/pi_rsi/tasks/kaggle-spaceship-titanic/.venv/bin/python`
- Delta vs this node's untouched parent quick: **+0.00186**. Fold deltas vs parent: +0.00639, −0.00215, −0.00576, +0.00290, +0.00796 (three up, two down). Below fold std and folds do not move together.
- FamilyInGroup dropped (not shipped; n004-like): quick **0.80732** (folds [0.79702, 0.81232, 0.81988, 0.80638, 0.80101], n=6954, elapsed=10.8s). FamilyInGroup vs this ablation: **Δ −0.00129**. Fold deltas: 0, −0.00072, −0.01080, +0.00290, +0.00217 (fold 2 dropped).
- On `data/train.csv`: 2752 rows with FamilyInGroup>1, transported 0.55087 vs 0.46359 otherwise (matches the hypothesized rate gap).
- Shipped hypothesized FamilyInGroup code. Final git commit: `fb23dd292259c5f4348e982f4aed26f03180a022`.
## Mechanism
The same-name-in-group outcome gap is real, but the integer count is almost GroupSize. FamilyInGroup equals GroupSize on 84.9% of `data/train.csv` rows (corr 0.830). The residual is small: 263 rows in multi-person groups with no same-name mate, plus 79 with GroupSize>1 and missing Name. LightGBM does split on it (full-train split count 363, rank 12, next to GroupSize 424), so it is not ignored, but those extra splits did not move folds together. The +0.00186 vs n006 is inside noise and is at least partly from dropping LastNameSize/CabinOccupancy rather than from the family count: adding FamilyInGroup onto n004-like features scored 0.80603 vs 0.80732 without it.
## Dead ends
- Integer FamilyInGroup: quick 0.80603 vs parent 0.80417 (mixed folds) and vs n004-like 0.80732 (fold 2 −0.01080). Do not stack more within-group surname *counts* on this LightGBM; GroupSize already encodes almost the same integer.
- Did not retry LastNameSize or CabinOccupancy (n006 dead ends) and did not count names on a train+predict concat.
## Next hypotheses
- Ablate integer GroupId: drop the numeric gggg from NUM_FEATURES; n001 still holds official validation (0.8177) while n004/n006 grouping extras did not, and FamilyInGroup did not either.
- Remaining CryoSleep NA and spend mix: after spenders-awake, set leftover CryoSleep NA to True when total spend is 0, and add luxury vs food/shopping spend shares (reviewer preference: cryo-consistent imputation and spend structure).
- Ablate n004 unique-group fill + deck→planet map (and drop FamilyInGroup if this node's official score is flat): return toward the n001 feature set instead of stacking more group/name counts.
## Open questions
- +0.00186 vs n006 is inside fold std and mixed across folds; if official validation is flat or down, treat FamilyInGroup as noise and do not keep it in later stacks.
- n001 remains the official best (0.8177). n004 lost validation; n006 was no_change; this family count did not beat n004 on worker quick. Prefer ablating GroupId / n004 imputation over another grouping feature.
- A binary HasSameNameMate (FamilyInGroup>1) was not tested; it would differ from GroupSize>1 on only 342 rows, so it is unlikely to beat the integer count that already failed.
