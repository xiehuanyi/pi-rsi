# Handoff n002: Wide regularized linear model
## Hypothesis
Keep a linear / log-target model but expand features: integer maps for ordinal quality/condition columns, train-only one-hot of Neighborhood, MSZoning, BldgType, HouseStyle, Foundation, GarageType, and SaleCondition (rare levels bucketed), train-median numeric imputation, log1p of skewed areas, plus TotalSF and TotalBath. Fit StandardScaler + RidgeCV (or ElasticNetCV) on log1p(SalePrice).
## What I did
- Replaced `src/features.py` with `WideLinearFeatures`: 19 ordinal maps, 7 train-only one-hots with min-count-5 Other bucket, median-imputed numerics, log1p of LotArea/GrLivArea/TotalBsmtSF/1stFlrSF/GarageArea, log1p(TotalBsmtSF+1stFlrSF+2ndFlrSF), and FullBath+0.5*HalfBath+BsmtFullBath+0.5*BsmtHalfBath. Stats and dummy levels fit on the labeled train frame only.
- Replaced `src/model.py` `RidgeLogModel` with StandardScaler + RidgeCV. Alpha grid started at 1–100; GCV sat on 100, so the grid was widened to `logspace(0, 3, 31)` (1–1000). Chosen alpha on full public train was ~200.
- Wired `train.py` to the new transformer and model. CLI and `Id,SalePrice` output unchanged.
- Compared ElasticNetCV on the same 5 folds as the evaluator; did not switch (delta inside fold noise).
## Result
- quick, untouched baseline: score 0.16778, folds [0.1461, 0.16809, 0.15892, 0.14038, 0.22542], std 0.0304, sem 0.0136, n=1167, elapsed 5.7s. Command: `eval/eval.py --seedset quick` with the task venv python.
- quick, wide RidgeCV: score 0.13125, folds [0.11296, 0.13245, 0.10657, 0.12831, 0.17596], std 0.0243, sem 0.01087, n=1167, elapsed 6.3s. Same command.
- Drop vs baseline quick: 0.03653, larger than baseline fold std. Parent official validation was 0.18359 (not re-run here).
- Final git commit: `40a8222fa116d5a6c2ccbedf4a392425e185411d`
## Mechanism
The 8-column ridge had OverallQual, size, garage, baths, and year but no neighborhood, zoning, building type, or the quality ratings that buyers actually pay for (ExterQual, KitchenQual, BsmtQual, …). One-hot Neighborhood plus ordinal quality maps let a linear log-price model pick up location premia and finish level. Log areas and TotalSF match the RMSLE/log-target scale. Regularization (alpha ~ 200–300 on most folds) keeps the ~110-column dummy-expanded matrix from blowing up.
## Dead ends
- RidgeCV alphas 1–100: GCV chose the cap (100). Widening to 1–1000 moved the choice to ~200 (full train) / 63–316 (per fold). Not a failed idea, but the stated 1–100 grid was too tight for this width.
- ElasticNetCV (l1_ratio in {0.1,0.3,0.5,0.7,0.9}, nested 5-fold, same evaluator folds): mean 0.12966 vs Ridge 0.13125. Delta 0.0016 << fold std 0.024; l1_ratio always 0.1 (almost ridge). Kept RidgeCV.
## Next hypotheses
- 1. Robustify the linear model to Ames “partial-sale palace” outliers: Id 1299 (Edwards, GrLivArea=5642, TotalBsmtSF=6110, SalePrice=160000) is in public train and alone drives fold 4 from ~0.11 to 0.176 (ridge predicted ~1.27e6). Id 524, the usual twin, is not in public train and may sit in the hidden holdout — so dropping 1299 from train is not enough; winsorize/cap area features at a train quantile (e.g. 99th or 4000 sqft) on both train and predict, or use HuberRegressor.
- 2. LightGBM or CatBoost on these features (CatBoost can take the 7 categoricals natively). Trees should cut the Edwards extrapolation and capture quality×size interactions ridge treats as additive. Keep log1p target, 5-fold the same way, modest depth/leaves so 1167 rows do not overfit.
- 3. Blend this RidgeCV with one GBDT (simple average or CV-stacked meta ridge on OOF preds). Linear model is already strong on typical houses; trees should cover the residual tail.
## Open questions
- Is Id 524 (Edwards, GrLivArea=4676, SalePrice=184750) in the hidden 293-row holdout? If yes, official validation may still look like fold 4 until areas are capped or a tree/blend is used.
- Id 1183 (NoRidge, GrLivArea=4476, SalePrice=745000) is a real expensive house in public train; any cap must not flatten legitimate luxury sales.
- Remaining unused high-signal cats: Condition1, Exterior1st, SaleType, MSSubClass-as-category. Worth adding only after outliers are handled, else more dummies just help the model overfit 1299-style rows.
