# Handoff n013: F-deck leftover HomePlanet from spend mix
## Hypothesis
After unique-group fill and the hard A/B/C/T/G deck→planet map, leftover HomePlanet NA on F-deck are Earth or Mars (never Europa). Fit a tiny LightGBM-free classifier on known F-deck rows using amenity mix (Mars luxury share ~0.14 vs Earth ~0.40, plus room-service share and zero-spend) and apply it only to leftover F-deck NA inside each frame. Do not hard-map all F to Earth. Leave E/D/missing-cabin NA as NA.
## What I did
- Left the CLI contract in `train.py` and LightGBM hyperparameters in `src/model.py` unchanged.
- `src/impute.py`: `fill_f_deck_homeplanet` / `_f_deck_spend_mix_planet` — per-frame LogisticRegression (luxury share, room-service share, zero-spend) fit on known F-deck Earth/Mars rows; applied only where Deck==F and HomePlanet is still NA. No bulk F→Earth map.
- `src/features.py`: call that fill after unique-group HomePlanet fill and the hard deck map. E/D/missing-cabin NA are untouched.
- Tried unique last-name→planet among known F first (allowed by the hypothesis); worker ablation showed it hurt, so it is not in the shipped commit.
- Did not concatenate train+predict. Did not modify `eval/` or `docs/`.
## Result
- Untouched parent quick: score **0.80718** (folds [0.79773, 0.8159, 0.81124, 0.80783, 0.80318], n=6954, elapsed 11.2s).
- Shipped spend-mix LR (leftover F only) quick: score **0.80760** (folds [0.80057, 0.81519, 0.8098, 0.81001, 0.80246], score_std=0.00537, score_sem=0.0024, n=6954, elapsed 11.0s).
- Command: `~/pi-rsi/pi_rsi/tasks/kaggle-spaceship-titanic/.venv/bin/python eval/eval.py --seedset quick --python ~/pi-rsi/pi_rsi/tasks/kaggle-spaceship-titanic/.venv/bin/python`
- Delta vs this node's untouched quick: **+0.00042**. Fold deltas vs parent: +0.00284, −0.00071, −0.00144, +0.00218, −0.00072 (three down). Below fold std; treat as no change on quick.
- Worker same-fold ablations (group split seed 20260910, matches parent folds): parent-like 0.80718; last-name only **0.80475**; spend-mix only **0.80760**; last-name+mix 0.80660 (also official quick 0.80660, score_std=0.00489).
- On `data/train.csv`, leftover HomePlanet NA after n004 fills is 49 (F 33, E 9, D 3, missing-cabin 4). Shipped fill: F 33→0 (Earth/Mars only); remaining HomePlanet NA **16** (E/D/missing-cabin). test.csv leftover F 16 filled; remaining NA 14.
- Final git commit: `15411ee95a396d7001694b8c1434a13dde6768d5`
## Mechanism
F-deck is Earth or Mars. Among known F spenders, Mars luxury share is ~0.15 vs Earth ~0.40 and Mars room-service share is ~0.49 vs Earth ~0.20; F zero-spend is 490 Mars vs 19 Earth, so zeros look like Mars, not a global F→Earth majority. A 3-feature logistic fit on known F reaches ~0.84 planet accuracy, but that planet guess is almost the same axis LightGBM already has from log amenities and spend shares. Leftover F is only 33/6954 rows, so even a perfect fill can move accuracy by a few predictions. Spend mix also tracks Transported (known F Earth ~0.29 transported vs Mars ~0.64), so writing the guess into HomePlanet can leak label signal. Last names uniquely determine planet on this file (0 mixed surnames; group-LOO last-name→planet acc 1.0 on known F) but still span unrelated groups, and using that map as a HomePlanet fill made quick worse.
## Dead ends
- Unique last-name→planet fill for leftover F-deck NA: worker same-fold **0.80475** vs parent 0.80718 (Δ −0.00243). Do not retry surname→planet imputation; this is the n005/n006 last-name-span-groups failure in a new costume, even though planet accuracy is perfect.
- Last-name map plus spend-mix LR: official quick **0.80660** vs parent 0.80718 (Δ −0.00058). Last name is the drag.
- Luxury-only threshold on known F spenders (~0.55) is worse than majority Earth among spenders (~0.76) because many Earth F spenders also have low luxury. Need zero-spend and/or room-service, and even then accuracy does not move.
- Bulk-mapping deck F to Earth remains a dead end (n004); leftover F is mixed Earth/Mars. This node did not do that.
## Next hypotheses
- Ablate integer `GroupId`. It is a high-split LightGBM feature that encodes sequential gggg order in `data/train.csv`. n004 location NA-fill and this leftover-F fill both stay inside fold noise; if GroupId overfits the public file, dropping it should generalize better even if quick dips.
- Replace continuous `LuxuryShare`/`FoodShoppingShare` with one categorical spend pattern (Zero / Luxury / FoodShopping / RoomService from argmax amenity). The food-vs-luxury contrast is real; a 4-level category is less collinear than two shares plus five log spends (n009 shares-only was −0.00229).
- Do not add more leftover HomePlanet fills (E/D/missing-cabin, or a train-only F classifier). Leave remaining location NA as NA; n004 and this node both failed to beat parent on the only scores that matter.
## Open questions
- Official validation of n009 was already down vs n004 (0.8108 vs 0.8137). This node's +0.00042 quick is noise; do not expect the F-deck fill to recover holdout.
- Remaining 16 HomePlanet NA are E/D/missing-cabin. Should they stay missing, or is there a hard rule that is not spend mix / last name?
- Does integer GroupId still overfit sequential structure (open since n001 / n004 / n009)? Ablate it before adding more weak imputations.
- Zero-spend CryoSleep NA for children (age<13) is still untested; only 17 such rows here and n009 found the blanket True fill near noise.
