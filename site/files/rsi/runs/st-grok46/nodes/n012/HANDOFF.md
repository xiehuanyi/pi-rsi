# Handoff n012: Ablate integer GroupId
## Hypothesis
Drop integer GroupId from NUM_FEATURES and keep GroupSize, Deck/Side, and spend columns. GroupId is sequential gggg order in the public file and LightGBM split on it heavily (second only to CabinNum). If that column memorizes public-file order rather than a real group effect, removing it should help the hidden holdout even if quick dips slightly. Do not add features or retune trees.
## What I did
- Left the CLI contract in `train.py` and LightGBM hyperparameters in `src/model.py` unchanged.
- `src/features.py`: removed `GroupId` from `NUM_FEATURES` and stopped writing it in `FeatureBuilder._raw`. The gggg key is still used for unique group-mate fills and for `GroupSize`.
- Did not add features. Did not concatenate train+predict. Did not modify `eval/` or `docs/`.
- Worker diagnostic (not official eval): parent-like vs ablated LightGBM split counts on `data/train.csv`, plus GroupId–CabinNum correlation and consecutive-group deck/side overlap.
## Result
- Untouched parent quick: score **0.80718** (folds [0.79773, 0.8159, 0.81124, 0.80783, 0.80318], score_std=0.0063, score_sem=0.00282, n=6954, elapsed 11.0s).
- Shipped no-GroupId quick: score **0.80761** (folds [0.7956, 0.81805, 0.81628, 0.80348, 0.80463], score_std=0.00842, score_sem=0.00377, n=6954, elapsed 11.4s).
- Command: `~/pi-rsi/pi_rsi/tasks/kaggle-spaceship-titanic/.venv/bin/python eval/eval.py --seedset quick --python ~/pi-rsi/pi_rsi/tasks/kaggle-spaceship-titanic/.venv/bin/python`
- Delta vs this node's untouched quick: **+0.00043**. Fold deltas vs parent: −0.00213, +0.00215, +0.00504, −0.00435, +0.00145 (three up, two down). Below fold std; treat as no change on quick. Fold std rose 0.0063→0.00842.
- Official validation is not computed in this session.
- Final git commit: `742b6bbb6e9f85bebafc6b95fc91bf540beb6aa6`
## Mechanism
Integer GroupId is almost a second copy of CabinNum, not a deck-block id. On `data/train.csv` it correlates 0.681 with CabinNum and only 0.022 with Transported. Consecutive groups share Deck at 0.244 (about chance given the deck mix) and Side at 0.486, so nearby gggg values do not mark the same cabin wing. Parent-like LightGBM still spent 2158 splits on GroupId (rank 2, behind CabinNum 2220). After the drop those splits moved onto CabinNum (3054) and other existing numerics; GroupSize stayed in the model (581 splits). Quick accuracy therefore stayed flat: the booster already had the sequential cabin coordinate, and GroupId was not carrying a separate group-transport signal under group-aware folds.
## Dead ends
- Dropping GroupId does not move group-aware quick (0.80761 vs 0.80718, Δ +0.00043, mixed folds). Do not treat this as a quick win. Keep the ablation only as a generalization test against n001/n004 holdout drop; if official validation falls, restore GroupId before stacking more features.
- Consecutive-group deck/side overlap is not above chance, so “nearby groups share decks” is not a reason to keep integer gggg on this file. Do not reintroduce GroupId as a cabin-block proxy without a different encoding (e.g. binned CabinNum or deck-relative room).
## Next hypotheses
- Ablate or coarsen CabinNum next, same protocol (no new features, no tree retune). After dropping GroupId it is the dominant split feature (3054 splits, 1733 unique values) and is the sequential coordinate GroupId was duplicating. If public-file order is the leak, CabinNum is the remaining channel.
- Resolve leftover F-deck HomePlanet NA (33 of 49 remaining after n004 fills) with amenity mix, not a global Earth default. Mars spenders have luxury share ~0.145 vs Earth ~0.406 vs Europa ~0.491; remaining NA spenders sit in between (mean 0.36, median 0.15).
- Replace the two continuous spend shares with a single discrete spend-pattern categorical (argmax amenity, or Food vs Luxury vs RoomService vs Zero). n009 found LuxuryShare/FoodShoppingShare collinear with the five log1p amenity columns (shares-only quick 0.80503).
## Open questions
- Does official validation of this node recover any of the n001 0.8177 → n004 0.8137 drop, stay flat like quick, or fall? Only restore GroupId if validation falls.
- Is CabinNum itself overfitting sequential cabin numbering the same way GroupId was? Its label correlation is also weak (−0.045).
- Remaining F/E/D HomePlanet NA may still be better left missing than weakly imputed (n004 location fill already failed to transfer).
