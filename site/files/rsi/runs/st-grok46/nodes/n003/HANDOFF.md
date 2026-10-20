# Handoff n003: Group-level transported prior features
## Hypothesis
Passengers in the same gggg group share cabins and correlated outcomes. Add GroupSize, IsAlone, SameCabinAsGroup, and leave-one-out GroupTransportedMean / GroupOtherTransportedCount (exclude the row itself; at predict time use train-group stats if the group was seen else the global mean). Fill missing HomePlanet/Cabin from group-mates. Feed these plus spend/age/cryo/planet/deck basics into LightGBM, and shrink predict-set probabilities toward the in-batch group mean so the outcome-correlation prior can fire when groups do not overlap train.
## What I did
- Left the CLI contract in `train.py` (`--train/--predict/--out`, columns `PassengerId,Transported`).
- Added `src/group.py`: group id/size, mode-fill, LOO/lookup transported stats, `blend_group_proba`.
- Rewrote `src/features.py`: `FeatureBuilder` builds log spends, Age, GroupSize/IsAlone/SameCabinAsGroup, LOO group target columns, group-filled HomePlanet plus Deck/Side from the filled Cabin, and VIP/CryoSleep/Destination categoricals.
- Rewrote `src/model.py`: LightGBM (`n_estimators=500`, `learning_rate=0.05`, `num_leaves=31`, `random_state=42`, `n_jobs=1`).
- `train.py` blends row probabilities with the predict-batch group mean (strength 0.30) then thresholds at 0.5.
- Did not copy n001's GroupId/CabinNum or n002's cryo-spend rewrite. Did not change `eval/` or `docs/`.
## Result
- Untouched starter quick: score **0.76335** (folds [0.74947, 0.76504, 0.76369, 0.76432, 0.77424], score_std=0.00794, n=6954, elapsed=7.3s).
- Group features + LightGBM + blend quick: score **0.80073** (folds [0.78495, 0.80659, 0.80476, 0.79768, 0.8097], score_std=0.00882, score_sem=0.00395, n=6954, elapsed=10.5s).
- Command: `~/pi-rsi/pi_rsi/tasks/kaggle-spaceship-titanic/.venv/bin/python eval/eval.py --seedset quick --python ~/pi-rsi/pi_rsi/tasks/kaggle-spaceship-titanic/.venv/bin/python`
- Delta vs this node's starter quick: **+0.03738**. n001 (different hypothesis: GBDT + cabin/group parse) quick was 0.80331; we are −0.00258, inside fold noise. Parent official validation was 0.7717 (different seed set; not comparable 1:1). Validation was not computed in this node.
- Local same-fold ablation (eval shuffle seed 20260910, **not** official): dropping the LOO target columns and/or the 0.30 blend moved the mean by at most ~0.002, all inside score_std ~0.009.
- Final git commit: `8c816efaae0749f0dfb2509944e515384326ad9e`
## Mechanism
Groups are outcome-dependent (42.9% of size>1 groups are all-True or all-False) and HomePlanet is 100% consistent within a group, Cabin 93%. GroupSize, IsAlone, SameCabinAsGroup, and filling planet/cabin from mates therefore transfer to held-out groups. The **label** prior does not: train/test group overlap is 0, and group-aware CV holds out whole groups, so at predict time GroupTransportedMean is the global mean and GroupSeenInTrain is 0 for every row. Trees can use the LOO mean for grouped **training** rows and then never see that pattern at test, which is a train/test shift. Most of the jump from 0.76 to 0.80 is LightGBM plus group size and location/planet after fill, not the transported-mean column. Predict-time blending of probabilities toward the in-batch group mean is the only way correlated outcomes can affect held-out groups; a fixed 0.30 weight did not beat fold noise.
## Dead ends
- LOO GroupTransportedMean / GroupOtherTransportedCount / GroupSeenInTrain as tree features: local ablation 0.80073 (on) vs 0.80163 (off, no blend). No reliable gain; predict-time values collapse to the global mean.
- Fixed group-proba blend 0.30 or 0.50: |delta| ≤ 0.002 vs no blend on the same folds. Not worth treating as progress.
## Next hypotheses
- Replace the label group-mean with label-free group aggregates (mean CryoSleep, mean log spend, mean age, maybe last-name count) computed on the current frame so they exist for unseen groups.
- Learn the predict-time group consensus (blend weight or majority snap) on an inner group holdout instead of a fixed 0.30.
- Add cabin occupancy and surname frequency counts on top of GroupSize; they capture cabin-mates and mixed-name families that group id size misses.
## Open questions
- Does Destination group-fill help? Destination is only 88.8% consistent within group, unlike HomePlanet.
- If a future split ever overlapped groups, the lookup path in `src/group.py` would start to matter; current public train/test overlap is 0.
- 500 trees at lr=0.05 was not tuned; fold std ≈ 0.009, so do not treat sub-0.005 moves as real.
