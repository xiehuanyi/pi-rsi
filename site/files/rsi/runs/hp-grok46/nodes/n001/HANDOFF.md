# Handoff n001: LightGBM on full tabular features with ordinal/NA handling
## Hypothesis
Replace the 8-feature ridge with a single LightGBMRegressor trained on log1p(SalePrice). Use nearly all columns: ordinal quality fields as ordered integers (NA→0), numeric NAs filled with train medians, remaining categoricals label-encoded on train only with an UNK bucket, plus cheap engineered fields TotalSF, Age, RemodAge, HasGarage, HasBsmt. Conservative GBDT defaults (800 trees, lr 0.05, 31 leaves) and clip predictions to a positive range. Expected drop from ~0.18 toward ~0.12–0.14 RMSLE.
## What I did
- Replaced `src/features.py`: `TabularFeatures` fits on the labeled train frame only. 22 ordinal maps (ExterQual, BsmtQual, KitchenQual, HeatingQC, FireplaceQu, GarageQual, …, NA→0), train medians for 40 numerics, 22 label-encoded cats (Neighborhood, MSZoning, MSSubClass, …) with UNK for unseen/NA, engineered TotalSF=TotalBsmtSF+1stFlrSF+2ndFlrSF, Age=YrSold-YearBuilt, RemodAge=YrSold-YearRemodAdd, HasGarage, HasBsmt. 84 columns, no predict-file statistics.
- Replaced `src/model.py`: `LGBMLogModel` fits LGBMRegressor on log1p(y), predicts expm1, clips to [0.5·ymin, 1.5·ymax]. Params: n_estimators=800, learning_rate=0.05, num_leaves=31, min_child_samples=20, subsample=0.8, subsample_freq=1, colsample_bytree=0.8, n_jobs=1, all seeds=42. Label-encoded cats passed as LightGBM `categorical_feature`.
- Rewired `train.py` to the new builder + model. CLI `--train/--predict/--out` and `Id,SalePrice` unchanged.
## Result
- quick (untouched ridge): score 0.16778, folds=[0.1461, 0.16809, 0.15892, 0.14038, 0.22542], elapsed=5.5s. Command: `eval/eval.py --seedset quick`.
- quick (this node): score 0.12694, folds=[0.12405, 0.13612, 0.11611, 0.11892, 0.13949], score_std=0.00929, score_sem=0.00416, n=1167, elapsed=10.8s. Same command. Delta vs ridge quick: −0.04084.
- validation: not computed here (harness-only). Parent/root official validation was 0.18359.
- Final git commit: `7549b29c8cbc8dcbcd27c4b4027a656ee579e96b`.
## Mechanism
Ames sale prices are driven by many sparse, mixed-type fields (neighborhood, quality ratings, basement/garage finish, living area) that an 8-column ridge never sees. Mapping Ex/Gd/TA/Fa/Po to a monotone integer lets trees split on “better quality” without burning depth on unordered labels. Train-only medians and UNK encodings avoid leakage. TotalSF is the strongest LightGBM split feature (importance 1688 on a full-public-train fit), above LotArea/GarageArea/GrLivArea; Age and RemodAge also get used. Trees on log1p(SalePrice) match the RMSLE metric. Fold scores tightened (no 0.22 outlier fold), which is the pattern of a model that actually uses neighborhood/quality rather than a few size proxies.
## Dead ends
- HasGarage and HasBsmt got 0 LightGBM split gain on a full-public-train fit (redundant with GarageArea / TotalBsmtSF). They did not hurt the quick score; left in because they were part of this hypothesis. Do not treat them as valuable features in the next node unless an ablation shows otherwise.
- No failed training runs. No extra hyperparameter search in this node.
## Next hypotheses
- 1. Average LightGBM + XGBoost + CatBoost on the same `TabularFeatures`, train each on log1p(SalePrice), mean in log space, expm1. Complementary GBDT biases usually cut another ~0.005–0.015 RMSLE on Ames.
- 2. Add TotalBath, TotalPorchSF, and OverallQual×GrLivArea; drop or ignore zero-gain HasGarage/HasBsmt. Optionally exclude the Edwards GrLivArea>4000 cheap sales from training (classic Ames outliers).
- 3. Blend the current LGBM with a Ridge/ElasticNet on one-hot categoricals plus log-skewed area features. Linear residuals often complement trees and are the usual path into the 0.11–0.12 band.
## Open questions
- Does 800 trees overfit the hidden 293-row holdout relative to 300–500 trees or early stopping on an inner val split? Quick fold std is 0.00929, so sub-0.01 moves are noise on quick.
- Are integer ordinal maps better for LightGBM than leaving those columns as categoricals? Not ablated here.
- Neighborhood is used (importance 649) but target encoding with out-of-fold stats might do better than label codes.
