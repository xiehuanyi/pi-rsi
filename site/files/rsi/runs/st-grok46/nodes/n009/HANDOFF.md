# Handoff n009: CryoSleep remaining NA and spend mix
## Hypothesis
After the existing rule that spend>0 forces CryoSleep=False, set remaining missing CryoSleep to True when total amenity spend is 0 (cryosleepers never spend). Add two numeric features: luxury share (Spa+VRDeck)/TotalSpend and food/shopping share (FoodCourt+ShoppingMall)/TotalSpend, 0 when total is 0. Keep LightGBM.
## What I did
- Left the CLI contract in `train.py` and LightGBM hyperparameters in `src/model.py` unchanged.
- `src/features.py`: `impute_cryosleep` — spend>0 → CryoSleep False; remaining NA with total amenity spend == 0 → True. `spend_mix_shares` adds `LuxuryShare` and `FoodShoppingShare` (0 when total is 0). Both are in `NUM_FEATURES`.
- Did not retune log1p spends or tree hyperparameters. Did not concatenate train+predict. Did not modify `eval/` or `docs/`.
- Same-fold worker ablations (not official eval.py) of cryo-only vs shares-only vs both, plus LightGBM split-count importances on `data/train.csv`.
## Result
- Untouched parent quick: score **0.80732** (folds [0.79702, 0.81232, 0.81988, 0.80638, 0.80101], n=6954, elapsed 11.8s).
- Shipped cryo-zero-True + spend shares quick: score **0.80718** (folds [0.79773, 0.8159, 0.81124, 0.80783, 0.80318], score_std=0.0063, score_sem=0.00282, n=6954, elapsed 10.9s).
- Command: `~/pi-rsi/pi_rsi/tasks/kaggle-spaceship-titanic/.venv/bin/python eval/eval.py --seedset quick --python ~/pi-rsi/pi_rsi/tasks/kaggle-spaceship-titanic/.venv/bin/python`
- Delta vs this node's untouched quick: **−0.00014**. Fold deltas vs parent: +0.00071, +0.00358, −0.00864, +0.00145, +0.00217 (four up, fold 2 down). Below fold std; treat as no change on quick.
- Worker same-fold ablations (group split seed 20260910, matches parent folds): parent-like 0.80732; cryo-only **0.80791**; shares-only **0.80503**; both 0.80718.
- On `data/train.csv`, CryoSleep NA 186 → 0 (100 spenders forced False, 86 zero-spend NA set True).
- Final git commit: `5469a860e21c8013e79cc6d8f0a52c0ce7f78653`
## Mechanism
Cryosleepers never spend, and the 86 leftover CryoSleep NA with total bill 0 transport at 0.709 vs 0.810 for known cryo True and 0.300 for spend-NA (forced awake). That is the right direction, but 416 known-awake passengers also spend nothing, including 327 children under 13, so a blanket True fill is wrong for some rows (17 of the 86 NA are age<13). LightGBM already has log spends and log_TotalSpend, so CryoSleep is almost redundant after the spender-awake rule (only 146 splits, rank 17). Luxury vs food mix is a real label correlation among spenders (food/shopping share corr +0.504, luxury −0.329), and the booster does use the new columns (FoodShoppingShare 998 splits rank 5, LuxuryShare 775 rank 6). They are collinear with the five log1p amenity columns, so extra splits do not raise accuracy; shares-only was slightly worse than parent on the same folds.
## Dead ends
- Combined cryo-zero-True + two spend shares: quick 0.80718 vs parent 0.80732 (Δ −0.00014). Do not expect this bundle to beat n004 on hidden validation.
- Continuous LuxuryShare + FoodShoppingShare alone: worker same-fold **0.80503** vs parent 0.80732 (Δ −0.00229, higher fold std 0.00997). LightGBM used them; they still did not help. Do not retry these two collinear shares on top of log1p amenity columns.
- Zero-spend CryoSleep=True fill alone: worker same-fold **0.80791** vs parent 0.80732 (Δ +0.00059). Matches n002’s finding that cryo rules add ~0.001–0.004 once a booster already has spend columns. Not worth stacking as a standalone bet.
## Next hypotheses
- Ablate integer `GroupId`. It is the second-most-used LightGBM feature (2158 splits) and encodes sequential gggg order in `data/train.csv`. n004’s +0.004 quick lift from location NA-fill did not carry to official validation (0.8137 vs n001 0.8177); if GroupId overfits the public file, dropping it should generalize better even if quick dips.
- Resolve leftover F-deck HomePlanet NA (33 of 49 remaining after n004 fills) with amenity mix or last name (Earth vs Mars), not a global Earth default. Mars spenders have luxury share ~0.14 vs Earth ~0.40.
- Replace the two continuous spend shares with a single discrete spend-pattern categorical (argmax amenity, or Food vs Luxury vs RoomService vs Zero). The food-vs-luxury contrast is real; a 4-level category is less collinear than two shares plus five log spends.
## Open questions
- If official validation of this node is flat vs n004, treat cryo NA fill and spend shares as noise and do not stack more of either.
- Should zero-spend CryoSleep NA stay missing for children (age<13), where known labels are ~50/50 cryo True/False? Only 17 such rows here.
- Does integer GroupId still overfit sequential structure (open since n001 / n004)? Ablate it before adding more weak imputations.
- Remaining F/E/D HomePlanet NA may be better left missing than weakly imputed (n004 location fill already failed to transfer).
