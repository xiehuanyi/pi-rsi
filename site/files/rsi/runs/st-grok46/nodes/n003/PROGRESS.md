# PROGRESS n003: Group-level transported prior features

## 2026-09-10 start
- Node n003, parent root (official validation 0.7717). Global best n001 0.8177 (different hypothesis: GBDT + cabin/group parse).
- Hypothesis: GroupSize, IsAlone, SameCabinAsGroup, LOO GroupTransportedMean / GroupOtherTransportedCount, group-fill HomePlanet/Cabin; LightGBM or logistic on basics + these.
- Constraint: one hypothesis; do not bundle n001 cabin-parse GBDT. Group-aware CV means predict groups are disjoint from train, so label priors on predict collapse to global mean unless a group appeared in train.
- Next: measure untouched starter quick score, then implement.

## Before baseline eval
- Code is root starter: logistic on log-spend + age + CryoSleep.
- Command: `.venv/bin/python eval/eval.py --seedset quick --python .venv/bin/python`

## Baseline quick (untouched starter)
- seedset=quick, score **0.76335**, folds [0.74947, 0.76504, 0.76369, 0.76432, 0.77424], score_std=0.00794, n=6954, elapsed=7.3s
- Matches n001's reported starter quick score.

## Data facts (train.csv only; not a score)
- 6954 rows, 4977 groups; 44.5% of passengers in groups of size>1.
- Train/test group overlap = 0. Group-aware CV also holds out whole groups, so **label** group priors are unseen at predict (must fall back to global mean).
- Among size>1 groups, 42.9% are fully homogeneous on Transported (all True or all False). Mean |group-mean - 0.5| = 0.266 (not independent).
- HomePlanet is 100% consistent within group (67/152 NA fillable). Cabin 93.2% consistent (84/164 NA fillable).

## Implementation plan
- `src/group.py`: group id/size, mode-fill, LOO group target stats, predict-time lookup, optional group-proba blend.
- `src/features.py`: basics (log spend, age, cryo, vip, home/dest) + Deck/Side from **group-filled** Cabin + GroupSize/IsAlone/SameCabinAsGroup + LOO GroupTransportedMean/GroupOtherTransportedCount/GroupSeenInTrain.
- `src/model.py`: LightGBM, seed 42, 500 trees. Predict-time blend of row proba with in-batch group-mean proba (the only way correlated outcomes can fire when groups do not overlap train).
- Do not copy n001 GroupId/CabinNum; do not apply n002 cryo-spend rewrite.

## Sanity check (one group fold, same shuffle seed as eval)
- LOO math checks out for a size-2 group (smoothed).
- Predict-set GroupSeenInTrain is all 0; GroupTransportedMean is the train global mean. Confirms no group overlap.
- HomePlanet NA 128 -> 68 after group fill on that fold.
- Fold-0 acc ~0.78495 with or without blend (blend flipped 14 rows, net zero). Not an official score.

## Before first full quick eval of the hypothesis
- About to run eval/eval.py --seedset quick on LightGBM + group features + blend=0.30.

## Official quick eval 1 (full hypothesis: LOO target prior + blend 0.30)
- seedset=quick, score **0.80073**, folds [0.78495, 0.80659, 0.80476, 0.79768, 0.8097], score_std=0.00882, score_sem=0.00395, n=6954, elapsed=10.5s
- Delta vs starter quick: **+0.03738**.
- n001 (GBDT+cabin/group, different hypothesis) quick was 0.80331; we are -0.00258, inside fold noise.

## Local ablation on the same eval folds (NOT official; for choosing knobs)
- target+blend0.3: 0.80073 (matches official)
- target+blend0: 0.79958
- notarget+blend0.3: 0.79918
- notarget+blend0: 0.80163
- notarget+blend0.5: 0.79976
- target+blend0.5: 0.79931
- All within score_std ~0.009. Label prior and blend do not reliably beat GroupSize+fill+Deck/Side+LightGBM. Expected: groups never overlap, so GroupTransportedMean is constant at predict.

## Next
- Try group-level *feature* aggregates (cryo/spend/age means) that transfer without labels; if noise, keep the specified hypothesis and hand off.

## Decision
- Not chasing sub-std knobs. Official result of the stated hypothesis is quick **0.80073**.
- Label-prior columns stay on (default) so the node implements the hypothesis rather than silently dropping it after the ablation.
- Writing HANDOFF.md and proposals.json. Final train.py commit path: group.py + features.py + LightGBM + blend 0.30.
