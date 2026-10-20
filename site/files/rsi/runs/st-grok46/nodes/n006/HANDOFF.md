# Handoff n006: Surname and cabin occupancy
## Hypothesis
Parse last name from Name and, within each frame separately, add LastNameSize (count of passengers sharing that last name) and CabinOccupancy (count sharing the already-imputed Cabin string; 1 if cabin still missing). Keep LightGBM and current features. Families and cabin-mates often share Transported, and neither count is in the model now.
## What I did
- Left the CLI contract in `train.py` and LightGBM hyperparameters in `src/model.py` unchanged.
- In `src/features.py`: added `last_name`, `last_name_size`, `cabin_occupancy`. LastNameSize is the last whitespace token of Name, counted in the current frame only (0 if Name missing). CabinOccupancy counts the Cabin string after `impute_raw_shared_fields` (1 if Cabin still missing). Both sit in `NUM_FEATURES` next to GroupSize.
- Counts are never taken on a train+predict concat. `_raw` still transforms each frame on its own.
- Did not modify `eval/` or `docs/`.
- Ablated each count alone on the same quick seed set (not shipped).
## Result
- Untouched parent quick: score **0.80732** (folds [0.79702, 0.81232, 0.81988, 0.80638, 0.80101], score_std=0.00812, score_sem=0.00363, n=6954, elapsed=11.3s).
- LastNameSize + CabinOccupancy quick: score **0.80417** (folds [0.79063, 0.81375, 0.81484, 0.80638, 0.79522], score_std=0.00974, score_sem=0.00435, n=6954, elapsed=11.5s).
- Command: `~/pi-rsi/pi_rsi/tasks/kaggle-spaceship-titanic/.venv/bin/python eval/eval.py --seedset quick --python ~/pi-rsi/pi_rsi/tasks/kaggle-spaceship-titanic/.venv/bin/python`
- Delta vs this node's untouched quick: **−0.00315**. Fold deltas vs parent: −0.00639, +0.00143, −0.00504, 0, −0.00579 (three down, one up, one tied). Below fold std (~0.008) and not a consistent lift.
- CabinOccupancy-only (not shipped): quick **0.80460** (folds [0.79347, 0.80516, 0.81844, 0.80566, 0.80029], std=0.00819). All five folds down vs parent.
- LastNameSize-only (not shipped): quick **0.80534** (folds [0.78424, 0.8159, 0.82277, 0.80566, 0.79812], std=0.01351). Fold 0 dropped −0.01278; variance rose.
- Shipped hypothesized both-features code. Final git commit: `214cf049774b6c60604d0bd2b46cae687ada7702`.
## Mechanism
The family/cabin-mate outcome correlation is real, but these two *counts* are not the right encoding. LastNameSize is a global frequency: 1388 of 2090 surnames in `data/train.csv` appear in more than one passenger group (median 2 groups per surname, max 10), so the feature mostly ranks common Earth last names rather than marking a traveling family. That matches the known collision risk and the LastNameSize-only fold-0 crash. CabinOccupancy is almost GroupSize: no cabin is shared across groups, occupancy never exceeds group size, and 1001 rows have occupancy < GroupSize because a group split across cabins (corr with GroupSize 0.87). LightGBM already splits on GroupSize; the extra occupancy integer is a near-duplicate plus a split-cabin residual it did not use. Sharing a last name *inside the same group* is a better family definition (2752 rows, transported 0.551 vs 0.464 otherwise) and was not this node's feature.
## Dead ends
- LastNameSize + CabinOccupancy together: quick 0.80417 vs parent 0.80732; three folds down. Do not stack more global surname/cabin frequency counts on this LightGBM.
- CabinOccupancy alone: quick 0.80460, all five folds down. Integer cabin occupancy is redundant with GroupSize.
- LastNameSize alone: quick 0.80534 with std 0.01351 (parent 0.00812). Global surname frequency is noisy; do not retry it.
- Did not concatenate train+predict to count names/cabins (would leak and was forbidden).
## Next hypotheses
- Within-group family flag: count how many group-mates share this passenger's last name (0 if Name missing), not the global surname frequency that failed here.
- Remaining CryoSleep NA: set True when total amenity spend is 0 after the existing spenders-awake rule, and add luxury (Spa+VRDeck) vs food/shopping spend shares.
- Ablate integer GroupId: still an open n001/n004 question; if official validation keeps lagging worker quick, drop GroupId before adding more location/name counts.
## Open questions
- −0.003 is inside fold std (~0.008). If official validation is flat vs n004, treat this as noise and do not keep occupancy/surname-frequency features in later stacks.
- n004 already lost official validation vs n001 (0.8137 vs 0.8177). If this node also fails to beat n001, prefer ablating GroupId / n004 imputation over adding more grouping counts.
- A split-cabin flag (GroupSize > CabinOccupancy, 1001 rows) is the only occupancy residual orthogonal to GroupSize; it was not tested.
