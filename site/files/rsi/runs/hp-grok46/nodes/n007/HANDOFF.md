# Handoff n007: Bath/porch/QualArea features and Edwards outliers
## Hypothesis
On top of the n001 LightGBM pipeline, add TotalBath=BsmtFullBath+FullBath+0.5*(BsmtHalfBath+HalfBath), TotalPorchSF=WoodDeckSF+OpenPorchSF+EnclosedPorch+3SsnPorch+ScreenPorch, and QualArea=OverallQual*GrLivArea (missing addends filled with 0 from train-coerced numerics). Drop zero-gain HasGarage/HasBsmt. When fitting, drop train rows with GrLivArea>4000 and SalePrice<300000 (the Edwards partial-sale outliers) but still score every predict row. Same LGBMLogModel and CLI.
## What I did
- Confirmed untouched parent quick RMSLE 0.12694 (same folds as n001).
- Public train contains one cheap palace: Id 1299 Edwards GrLivArea=5642 SalePrice=160000 SaleCondition=Partial, sitting in quick fold 4. Id 1183 NoRidge 4476/745000 is kept. The other classic Edwards palace (Id 524) is not in public train.
- `src/features.py`: `add_engineered` now emits TotalBath, TotalPorchSF, QualArea and no longer emits HasGarage/HasBsmt. Added `drop_train_outliers` (GrLivArea>4000 and SalePrice<300000).
- `train.py`: drop outliers on the labeled train frame only, then the same `TabularFeatures` + `LGBMLogModel` (log1p target, clip `[0.5·ymin, 1.5·ymax]` unchanged). Predict file is never filtered.
- Smoke: 1167→1166 rows (only Id 1299), 85 features, test transform still 1459 rows.
## Result
- quick (untouched parent, this worktree): score 0.12694, folds=[0.12405, 0.13612, 0.11611, 0.11892, 0.13949], elapsed=10.4s. Command: `eval/eval.py --seedset quick`.
- quick (this node): score 0.12460, folds=[0.11906, 0.13459, 0.12197, 0.11501, 0.13235], score_std=0.00761, score_sem=0.0034, n=1167, elapsed=10.7s. Same command. Delta vs parent quick: −0.00234. Per-fold deltas: −0.00499, −0.00153, +0.00586, −0.00391, −0.00714. Four of five folds improved; fold 2 rose.
- Mean delta is smaller than parent fold std (0.00929), so this is a modest signal inside noise, not a 0.01-class leap.
- validation: not computed here (harness-only). Parent official validation was 0.1418. n005 ran a similar extras+drop bundle on the n004 blend and official rose to 0.14524.
- Final git commit: `8ee1ac422e5e99c4c7a4379c9baf568c6b68f3cb`.
## Mechanism
TotalBath / TotalPorchSF / QualArea give trees a single split on bath count, outdoor SF, and quality×size instead of having to recombine the parts. On a full-public-train fit after the drop, QualArea (1365) and TotalPorchSF (1085) sit just under TotalSF (1393); TotalBath is weaker (293). HasGarage/HasBsmt stay gone. Id 1299 is val in fold 4, so the train drop never touches that fit: fold 4’s −0.00714 is extras-only. Fold-4 RMSLE without Id 1299 (diagnostic): parent 0.11926 → this 0.11244. The Edwards drop still never removes Id 1299 from fold 4’s *validation* set, so that house is still predicted like a real palace (this node 467199 vs 160000, ~2.92×; parent 485928 vs 160000, ~3.04×). Fold 3’s −0.00391 is the expected training-side effect: without 1299 in the fit, the genuine NoRidge palace in that val fold is no longer pulled toward a cheap-palace leaf. The same mechanism is a holdout risk: if Id 524 lives in the hidden 293, this model will overpredict it ~3× and can erase the quick gain — n005 already saw that on a blend.
## Dead ends
- Dropping the cheap palace does not fix it when it is the point you must predict. Fold 4 with Id 1299 is 0.13235; without that one row (diagnostic) it is 0.11244. QualArea did not rescue 1299 (still ~2.92× high).
- Did not ablate extras vs the row drop inside this node, so the −0.00234 is a bundle. Fold 4’s move is extras-only; fold 3’s move is the clue that the drop also affected a fold; fold 2 got worse (+0.00586).
- Mean quick drop 0.00234 ≪ parent fold std 0.00929; do not treat this as a large win before the hidden holdout. n005’s official regression on the same bundle is the prior.
## Next hypotheses
- 1. Ablate the cheap-palace row drop: keep TotalBath/TotalPorchSF/QualArea and the dropped flags, but fit on all labeled rows. Fold 4 here already improved without the drop (1299 is val). If folds 0/1/3 stay near this node and fold 2 recovers, extras are the real gain and holdout is safer if Id 524 is in the 293.
- 2. Keep the extras, do not drop train rows, and cap GrLivArea/TotalSF/TotalBsmtSF at a train-only quantile (e.g. 99th or 4000) on both train and predict. Dropping 1299 never helps when a twin palace is a prediction target; a shared cap changes the feature the tree sees at inference. Must not flatten Id 1183-style luxury sales.
- 3. Blend this LGBM+extras (no row drop) with n002’s Ridge on one-hot categoricals plus log-skewed area features, average in log space. Linear residuals differ from trees; remaining tails (partial sales, location) are the usual path into the 0.11–0.12 band. Do not equal-weight a linear member into a fold that it loses badly (n006 fold 4).
## Open questions
- Does the 0.00234 quick drop survive the hidden 293, or does Id 524 (if present) get the same ~3× overprediction as Id 1299 and wipe it out, as in n005?
- How much of folds 0/1/3 is the row drop vs the new columns? Fold 2’s +0.00586 is unexplained.
- Is TotalBath worth keeping given split gain 293 vs QualArea 1365 / TotalPorchSF 1085?
