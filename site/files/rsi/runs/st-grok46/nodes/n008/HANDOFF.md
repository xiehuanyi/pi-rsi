# Handoff n008: CryoSleep remaining NA and spend mix
## Hypothesis
After the existing rule that spend>0 forces CryoSleep=False, set remaining missing CryoSleep to True when total amenity spend is 0 (cryosleepers never spend). Add two numeric features: luxury share (Spa+VRDeck)/TotalSpend and food/shopping share (FoodCourt+ShoppingMall)/TotalSpend, 0 when total is 0. Keep LightGBM.
## What I did
- Left the CLI contract in `train.py` and LightGBM hyperparameters in `src/model.py` unchanged.
- In `src/features.py`: added `impute_cryosleep` (spenders → False, then remaining NA with total spend 0 → True) and `spend_share`. Put `LuxuryShare` and `FoodShopShare` in `NUM_FEATURES`. RoomService is the residual share and was not added.
- Confirmed on `data/train.csv`: 86 Cryo NA with spend 0 (transported 0.709) filled True; 100 Cryo NA with spend>0 stay False; 416 labeled-awake zero-spend rows stay False; 0 Cryo NA left on train or Kaggle test.
- Did not modify `eval/` or `docs/`.
- Ablated cryo-fill vs shares on the same quick seed set (not shipped).
## Result
- Untouched parent quick: score **0.80417** (folds [0.79063, 0.81375, 0.81484, 0.80638, 0.79522], score_std=0.00974, score_sem=0.00435, n=6954, elapsed=11.1s).
- Cryo remaining-NA True + LuxuryShare/FoodShopShare quick: score **0.80748** (folds [0.79276, 0.8159, 0.81772, 0.80856, 0.80246], score_std=0.00915, score_sem=0.00409, n=6954, elapsed=11.4s).
- Command: `~/pi-rsi/pi_rsi/tasks/kaggle-spaceship-titanic/.venv/bin/python eval/eval.py --seedset quick --python ~/pi-rsi/pi_rsi/tasks/kaggle-spaceship-titanic/.venv/bin/python`
- Delta vs this node's untouched quick: **+0.00331**. Fold deltas vs parent: +0.00213, +0.00215, +0.00288, +0.00218, +0.00724 (all five up). Inside the hypothesized +0.002 to +0.006 band and still below fold std (~0.009).
- Cryo-fill only (not shipped): quick **0.80562** (folds [0.78779, 0.81519, 0.82205, 0.80856, 0.7945], std=0.01274). Delta +0.00145; two folds down; variance up.
- Shares only (not shipped): quick **0.80722** (folds [0.7885, 0.81304, 0.817, 0.81218, 0.80535], std=0.01008). Delta +0.00305; two folds down.
- Shipped hypothesized both-parts code. Final git commit: `fc997188a307918e00fee64e0ba439669fdc7849`.
- Official validation is computed by the harness after this node; not measured here.
## Mechanism
Spend mix is a composition signal on top of log1p magnitudes: luxury share correlates with Transported at −0.446 on `data/train.csv` (raw Spa+VRDeck spend −0.275). LightGBM used both new columns (full-train split counts: FoodShopShare 862 rank 6, LuxuryShare 724 rank 8, above several log-amenity columns), so they were not ignored as collinear. Filling the 86 leftover CryoSleep NA as True when spend is 0 matches the domain rule that cryosleepers never spend and the 0.71 transported rate of those rows (vs 0.30 when NA and spend>0). The fill is slightly noisy: 416 labeled-awake passengers also spend 0 (transported 0.596 vs 0.810 for known cryosleepers). Shares carried most of the mean lift; the cryo fill added little on its own but was the difference between mixed folds and all five up. Combined quick 0.80748 only ties n004's 0.80732 while still carrying n006's LastNameSize/CabinOccupancy.
## Dead ends
- Cryo remaining-NA fill alone: quick 0.80562 vs parent 0.80417; mixed folds and higher std (0.01274). Matches n002: once the booster has spend columns, extra cryo rules add ~0.001–0.004 and are not a jump.
- Do not add RoomService share: on spenders it equals 1 − LuxuryShare − FoodShopShare (max residual 2e-16).
- Do not retry raw vs log1p amenity transforms (n002: both 0.79655 under HGB).
- Unique group-mate CryoSleep fill is too thin to replace the zero-spend rule: only 57 of 186 NA have a unique known mate (29 True / 28 False), and 642 groups already mix CryoSleep.
## Next hypotheses
- Ablate integer GroupId while keeping this node's cryo fill and spend shares: GroupId still takes 1945 splits (rank 2) but group-aware CV holds out whole groups, so those splits cannot name unseen passengers.
- Within-group family flag: count group-mates who share this passenger's last name (0 if Name missing), not global LastNameSize, which n006 already showed is noisy.
- Ablate LastNameSize and CabinOccupancy while keeping this node's cryo fill and spend shares: n006 dropped quick 0.80732→0.80417, and this node only recovered to 0.80748 with those counts still on.
## Open questions
- +0.00331 is below fold std (~0.009) even though all five folds moved up. If official validation is flat vs n006 (0.8166) or n001 (0.8177), treat this as a small generalize-friendly tweak, not a new ceiling.
- n001 remains the official best (0.8177). n004 imputation and n006 global counts have not beaten it; prefer ablating GroupId / n006 counts over stacking more features if this node also misses n001.
- LastNameSize still gets 883 splits despite n006's negative quick result; trees may be ranking common Earth names. Replacing it with a within-group family count is cleaner than leaving both.
