# Handoff n001: Gradient boosting + cabin/group features
## Hypothesis
Replace logistic regression with LightGBM on richer tabular features: parse Cabin into deck/num/side; extract group id and group size from PassengerId; native categorical encoding for HomePlanet, Destination, VIP, CryoSleep; keep log1p spends + TotalSpend + Age. Impute Age with train median and force CryoSleep=False when any amenity spend > 0. Fixed seed, 500 trees. Expected jump from ~0.77 to ~0.80–0.81 because GBDT captures non-linear spend/cabin interactions the linear baseline misses.
## What I did
- Left the CLI contract in `train.py` (`--train/--predict/--out`, columns `PassengerId,Transported`).
- Rewrote `src/features.py`: `FeatureBuilder` fits Age median and category levels on train only; builds Deck/CabinNum/Side, GroupId/GroupSize, log1p spends + log_TotalSpend, and pandas categoricals. Spenders are forced awake.
- Rewrote `src/model.py`: `LGBMModel` is LightGBM (`n_estimators=500`, `learning_rate=0.05`, `num_leaves=31`, `min_child_samples=20`, subsample/colsample 0.8, `reg_lambda=1.0`, `random_state=42`, `n_jobs=1`).
- Did not change `eval/` or `docs/`.
## Result
- Untouched baseline quick: score **0.76335** (folds [0.74947, 0.76504, 0.76369, 0.76432, 0.77424], elapsed 5.6s).
- LightGBM + cabin/group quick: score **0.80331** (folds [0.79134, 0.80659, 0.81772, 0.80638, 0.7945], score_std=0.00947, score_sem=0.00424, n=6954, elapsed 10.4s).
- Command: `~/pi-rsi/pi_rsi/tasks/kaggle-spaceship-titanic/.venv/bin/python eval/eval.py --seedset quick --python ~/pi-rsi/pi_rsi/tasks/kaggle-spaceship-titanic/.venv/bin/python`
- Delta vs this node's baseline quick: **+0.03996**. Parent official validation was 0.7717 (different seed set; not comparable 1:1).
- Final git commit: `b42f6f6b1e8be385ac191fc21090a04c9aee5fff`
## Mechanism
Transport is a non-linear function of cryosleep, cabin location, and how people spend. Cryosleepers never spend and are much more likely to be transported; deck (especially B/C vs E) and starboard vs port also shift the rate; group size captures families vs solos. Logistic regression on log-spend + age + CryoSleep could only draw a linear boundary through that mix. Trees split on deck/side/cryo and on spend tails separately, which is why every group-aware fold moved from the 0.75–0.77 band into 0.79–0.82. Forcing spenders awake removed a real label contradiction (100 train rows with spend>0 and missing CryoSleep).
## Dead ends
- None. Did not run extra knobs (early stopping, CatBoost, extra name features) on this node so the gain is attributable to the stated hypothesis.
## Next hypotheses
- Group-consistent missing imputation: fill HomePlanet/Cabin/Destination from group-mates (and deck→planet rules) inside each frame so missingness is not treated as a separate state.
- Surname and cabin occupancy: last-name group size and passengers-sharing-a-cabin as numeric counts; families often share outcomes.
- Spend mix + remaining CryoSleep NA: luxury (Spa+VRDeck) vs food/shopping shares, and impute CryoSleep=True when total spend is 0 and the flag is still missing.
## Open questions
- Does integer GroupId (booking order) generalize to the hidden holdout, or does it overfit sequential structure in `data/train.csv`? If validation lags quick, ablate GroupId first.
- 500 trees at lr=0.05 was not tuned; early stopping on a group holdout inside `train.py` might shave variance but is easy to confuse with real gains (fold std ≈ 0.009).
- Deck T has only 5 rows; rare-category handling is fine for LightGBM but a deck→planet imputer should special-case it.
