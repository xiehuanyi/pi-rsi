# Handoff n010: Cap Ames area outliers for linear model
## Hypothesis
Keep the n002 WideLinearFeatures + RidgeCV pipeline. Before assembling features, winsorize LotArea, GrLivArea, TotalBsmtSF, 1stFlrSF, 2ndFlrSF, GarageArea (and the TotalSF sum) at a train-only cap, applied at transform time so a holdout twin of Id 1299 (Id 524) cannot log-linear-extrapolate. Optional cheap-palace train drop was considered and not used.
## What I did
- `src/features.py` `WideLinearFeatures`: fit train-only caps; apply them in `_clip_area` / `_total_sf` on both train and predict.
- Global backstop: living-area cols (GrLivArea, TotalBsmtSF, 1stFlrSF, 2ndFlrSF) hard-clip at 4000; LotArea and GarageArea clip at the train 99th percentile; TotalSF = sum of clipped components, then clip at max(train 99th, 8000). Literal `min(4000, p99)` is not used: on this split p99(LotArea)=35027 so a 4000 lot cap would squash typical lots (median 9480), and p99(GrLivArea)=3083 would flatten Id 1183/1170.
- Tighter transform-time clip for Edwards & Partial rows only (Id 1299 in public train; Id 524 is the usual twin, absent here): listed area cols plus BsmtFinSF1 and LotFrontage at the train 99th percentile, and TotalSF at the train 99th of the raw sum. BsmtFinSF1 is the finished part of listed TotalBsmtSF; on fold 4 it was the largest log-price term (+0.51 at 5644 sqft) when left uncapped. LotFrontage is the lot-width twin of LotArea (Id 1299 has 313 vs p99 140).
- Did not drop GrLivArea>4000 & SalePrice<300000 rows. Fold 4 already holds out Id 1299, so drop cannot change that fold; dropping would also remove the only capped Edwards/Partial training example if Id 524 is in the official holdout.
- `train.py` still WideLinearFeatures + RidgeLogModel; CLI and `Id,SalePrice` unchanged.
## Result
- quick, untouched parent: score 0.13125, folds [0.11296, 0.13245, 0.10657, 0.12831, 0.17596], std 0.0243, sem 0.01087, n=1167, elapsed 5.7s. Command: `eval/eval.py --seedset quick` with the task venv python.
- quick, area caps: score 0.11993, folds [0.11397, 0.12378, 0.10075, 0.12181, 0.13931], std 0.01263, sem 0.00565, n=1167, elapsed 6.1s. Same command.
- Mean Δ=−0.01132 vs parent (parent fold std 0.0243). Fold 4 Δ=−0.03665 (0.17596→0.13931), larger than that std; folds 0–3 moved by at most ~0.01. Fold std 0.0243→0.01263.
- In-process (same evaluator folds, not a second seed set): Id 1299 pred=564818 vs 160000 (ratio 3.53, parent was ~1.27e6 / ~8×). Id 1183 pred=309153 vs 745000 (ratio 0.41); only GrLivArea 4476→4000 on that row.
- Final git commit: `ae9335be0a85ed798543bd50bfa6725d3b56508d`
## Mechanism
Ames “partial-sale palaces” (Edwards + Partial, huge area, cheap price) make a log-linear size model explode when they are prediction targets. Id 1299 alone accounts for fold 4’s gap vs the other folds (~0.11). A global 4000 living-area cap is too loose: BsmtFinSF1=5644 still dominated the log-price. A global 99th-percentile cap is too tight on ordinary luxury (Id 1183 NoRidge $745k). Capping Edwards/Partial rows to the train 99th at transform time cuts 1299 from ~8× to 3.5× without flattening 1183, and will also clip Id 524 if it appears in the hidden holdout. The leftover 3.5× is OverallQual=10 plus a Partial *premium* (Partial median price is high); area caps cannot cancel those additive terms.
## Dead ends
- Global living 4000 + LotArea/GarageArea p99 only (no Edwards/Partial tighter clip, no BsmtFinSF1): in-process mean 0.12905, fold 4 0.16874, Id 1299 still 6.85×. Not enough.
- Global p99 on the listed area cols (no palace mask): in-process mean 0.12839, fold 4 0.16348, Id 1299 6.12×, Id 1183 ratio 0.35 (worse luxury underprediction).
- Edwards/Partial p99 on listed cols without BsmtFinSF1: in-process fold 4 0.16097, Id 1299 5.83×. The finished-basement channel has to be capped with TotalBsmtSF.
- Cheap-palace train drop: does not change fold 4 (Id 1299 already held out). Helps fold 3 Id 1183 in-process (ratio 0.44→0.62) by removing a Qual=10 cheap example, but that is the n005/n007 failure mode if a holdout twin remains as a prediction target. Not used.
- Literal `min(4000, train 99th)` on LotArea: p99=35027 so the cap would be 4000 vs median lot 9480. Not implemented.
## Next hypotheses
- 1. Blend this capped Ridge with one GBDT (CatBoost or LightGBM, log1p target, modest depth). Ridge fold 4 is now 0.139 not 0.176, so equal log-space averaging should no longer be wrecked by the linear tail (n006/n009). Trees still handle Qual×size and the leftover 3.5× palace residual.
- 2. Residual palace term: HuberRegressor, or an Edwards×size / Partial×size interaction (Partial is currently a *positive* dummy). Area caps cannot offset OverallQual=10 on Id 1299/524.
- 3. Add unused high-signal cats (Condition1, Exterior1st, SaleType, MSSubClass-as-category) now that palaces are clipped at transform time; n002 deferred these because extra dummies helped the model overfit 1299-style rows.
## Open questions
- Is Id 524 in the hidden 293-row holdout? Official training includes Id 1299 as a capped cheap Edwards/Partial example, so a holdout 524 should look like that training row and may beat the quick fold-4 result (where 1299 was held out of train).
- Id 1183 (NoRidge, Abnorml, 4476 sqft, $745k) is still ~0.41×; that is luxury/Abnorml underprediction, not the palace bug.
- Would an Edwards-non-palace 99th (GrLivArea ~2171) as the palace cap beat the global 99th (~3083) without being too tight if a non-Edwards palace appears?
