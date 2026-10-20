# Handoff n003: CatBoost native categoricals with minimal FE
## Hypothesis
Use CatBoostRegressor with native categorical handling (all object/string columns plus MSSubClass), train on log1p(SalePrice), and keep feature engineering minimal: train-only numeric medians, categorical NA → 'Missing', plus TotalSF and house Age. iterations≈1000, depth≈6, learning_rate≈0.05, l2_leaf_reg≈3, fixed seed; optional early stopping on a small internal holdout of the train file only; predict with expm1.
## What I did
- Replaced `src/features.py` with `CatBoostFrameBuilder`: drops Id/SalePrice; forces MSSubClass to categorical; fills numeric NAs with train medians; fills cat NAs with 'Missing' and casts to str; adds `TotalSF = TotalBsmtSF + 1stFlrSF + 2ndFlrSF` (missing addends as 0) and `Age = YrSold - YearBuilt`. 37 numeric + 44 cat = 81 columns. No predict-file statistics.
- Replaced `src/model.py` with `CatBoostLogModel`: CatBoostRegressor on log1p(y), expm1 then clip to ≥1. Params: iterations=1000, depth=6, learning_rate=0.05, l2_leaf_reg=3, random_seed=42, thread_count=1, allow_writing_files=False. A seeded 12% holdout of the training frame (never the predict file) picks an iteration count via early_stopping_rounds=50; the model is then refit on the full training frame with max(best+1, 100) trees.
- Rewired `train.py` to the builder + CatBoost model. CLI `--train/--predict/--out` and `Id,SalePrice` unchanged.
## Result
- quick (untouched ridge): score 0.16778, folds=[0.1461, 0.16809, 0.15892, 0.14038, 0.22542], n=1167, elapsed=5.8s. Command: `eval/eval.py --seedset quick` with the task venv python.
- quick (this node): score 0.12187, folds=[0.11096, 0.1298, 0.10497, 0.1209, 0.14271], score_std=0.01344, score_sem=0.00601, n=1167, elapsed=107.4s. Same command. Delta vs ridge quick: −0.04591.
- validation: not computed here (harness-only). Parent/root official validation was 0.18359. n001 LightGBM official validation was 0.1418; n001 quick was 0.12694 (this CatBoost quick is 0.00507 lower than that, but fold std here is 0.01344 so treat the LGBM comparison as suggestive, not a confirmed win).
- Smoke on full public train: n_iter=723, pred range about 53k–556k, 32.5s for probe+refit.
- Final git commit: `9f9b98359d7ce9f8e7c7bc39faa68f0dfe60e378`.
## Mechanism
Ames prices are driven by mixed-type fields (Neighborhood, quality ratings, dwelling subclass, basement/garage finish) that an 8-column ridge never sees. CatBoost’s ordered target statistics encode those categoricals during training without a separate label-encode step, which is a different mechanism from n001’s LightGBM label codes and from a wide linear one-hot model. Log1p training matches RMSLE. TotalSF and Age give the trees the same size/age axes n001 found useful, without ordinal maps or extra flags. Early stopping on an internal 12% split (723 trees on the full-public smoke) limits overfit on ~900-row fold trains, then the refit uses every labeled row. The ridge’s 0.225 outlier fold dropped to 0.143, the pattern of a model that actually uses neighborhood/quality rather than a few size proxies.
## Dead ends
- No failed training runs. No extra hyperparameter search and no second model in this node.
- Early stopping vs a fixed 1000 trees was not ablated; the 12% holdout is noisy on ~110 rows, so the chosen iteration count may vary across folds. Do not treat 723 as a tuned optimum.
- HasGarage/HasBsmt were intentionally omitted (n001 dead end: zero LightGBM split gain). Not re-tested here.
## Next hypotheses
- 1. Log-space blend of this native-cat CatBoost with an n001-style LightGBM (ordinal quality maps + label-encoded remaining cats on the same log1p target). Equal-weight mean of log predictions, then expm1. Complementary encodings (ordered TE vs monotone integers/label codes) should cut residual error if the two models disagree on neighborhood and quality.
- 2. Keep CatBoost native cats for unordered fields, but map quality/condition columns (ExterQual, KitchenQual, BsmtQual, HeatingQC, FireplaceQu, GarageQual, …) to monotone integers with NA→0 and pass those as numeric. n001 found those maps used as split features; CatBoost currently treats Ex/Gd/TA as unordered labels.
- 3. On this CatBoost only, add RemodAge, TotalBath, TotalPorchSF (missing addends as 0) and drop train rows with GrLivArea>4000 and SalePrice<300000 (Edwards partial sales). Do not change the model class.
## Open questions
- Does the internal 12% early-stop split help or hurt vs always using 1000 trees? Quick fold std is 0.01344, so sub-0.01 moves are noise.
- Are monotone ordinal maps better for CatBoost than leaving Ex/Gd/TA as native cats? Not ablated here.
- Worst fold is still 0.14271 (ridge’s 0.22542 fold). Is that a few large homes, or a neighborhood CatBoost’s ordered TE underfits on a 930-row train?
