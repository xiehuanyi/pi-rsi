# Handoff n005: Ames extras + Edwards outliers
## Hypothesis
Keep BlendLogModel and TabularFeatures, but add TotalBath (BsmtFullBath+0.5*BsmtHalfBath+FullBath+0.5*HalfBath), TotalPorchSF (WoodDeck+OpenPorch+Enclosed+3Ssn+Screen), and OverallQual*GrLivArea; drop HasGarage and HasBsmt. When fitting, drop training rows with GrLivArea>4000 in Neighborhood Edwards (or SalePrice<300000 and GrLivArea>4000). Apply the same clip. Goal is the remaining 0.13762 quick fold, which barely moved under the tree blend.
## What I did
- Confirmed untouched parent quick RMSLE 0.12053 (same folds as n004).
- Public train contains one cheap palace: Id 1299 Edwards GrLivArea=5642 SalePrice=160000, sitting in quick fold 4. Id 1183 NoRidge 4476/745000 is kept. The other classic Edwards palace (Id 524) is not in public train.
- `src/features.py`: `add_engineered` now emits TotalBath, TotalPorchSF, QualGrLiv and no longer emits HasGarage/HasBsmt. Added `drop_train_outliers` (Edwards GrLivArea>4000 OR GrLivArea>4000 with SalePrice<300k).
- `train.py`: drop outliers on the labeled train frame only, then the same `TabularFeatures` + `BlendLogModel` (log-space equal blend, clip `[0.5·ymin, 1.5·ymax]` unchanged). Predict file is never filtered.
- Smoke: 1167→1166 rows (only Id 1299), 85 features, test transform still 1459 rows.
## Result
- quick (untouched parent, this worktree): score 0.12053, folds=[0.11526, 0.12763, 0.10596, 0.11617, 0.13762], elapsed=62.1s. Command: `eval/eval.py --seedset quick`.
- quick (this node): score 0.11818, folds=[0.11371, 0.12694, 0.10627, 0.10948, 0.13452], score_std=0.01078, score_sem=0.00482, n=1167, elapsed=62.5s. Same command. Delta vs parent quick: −0.00235. Per-fold deltas: −0.00155, −0.00069, +0.00031, −0.00669, −0.00310. Four of five folds improved; fold 4 (the 0.13762 tail) moved −0.00310.
- Mean delta is smaller than fold std (~0.011), so this is a modest consistent signal, not a 0.01-class leap.
- validation: not computed here (harness-only). Parent official validation was 0.1389.
- Final git commit: `5253670acd7a9835f69f6495b23b53f93d828ef0`.
## Mechanism
TotalBath / TotalPorchSF / QualGrLiv give trees a single split on bath count, outdoor SF, and quality×size instead of having to recombine the parts. That, plus dropping the two zero-gain flags, moved the bulk of every fold including fold 4’s non-palace houses (fold-4 RMSLE without Id 1299: parent 0.11117 → this 0.10887, diagnostic only). The Edwards drop never removes Id 1299 from fold 4’s *validation* set, so that house is still predicted like a real palace (this node 536995 vs 160000; parent 554699 vs 160000). Fold 3’s large −0.00669 is the expected training-side effect: without 1299 in the fit, the genuine NoRidge palace in that val fold is no longer pulled toward a cheap-palace leaf. The same mechanism is a holdout risk: if Id 524 lives in the hidden 293, this model will overpredict it ~3× and can erase the quick gain.
## Dead ends
- Dropping the cheap palace does not fix it when it is the point you must predict. Fold 4 with Id 1299 is 0.13452; without that one row (diagnostic) it is 0.10887. QualGrLiv did not rescue 1299 (still ~3.4× high).
- Did not ablate extras vs the row drop inside this node, so the −0.00235 is a bundle. Fold 3’s jump is the clue that the drop, not only the new columns, moved a fold.
- Mean quick drop 0.00235 ≪ fold std 0.01078; do not treat this as a large win before the hidden holdout.
## Next hypotheses
- 1. Ablate the Edwards row drop: keep TotalBath/TotalPorchSF/QualGrLiv and the dropped flags, but fit on all labeled rows. If quick folds 0/1/4 stay improved and only fold 3 gives back its −0.00669, extras are the real gain and holdout is safer if Id 524 is in the 293.
- 2. Keep this blend+extras and add a Ridge (or ElasticNet) on one-hot categoricals plus log-skewed area features as a fourth log-space member. n002’s linear model sat near 0.13 quick with different errors than trees; remaining fold-4 tails (Id 633 NWAmes 82500 vs ~173k, Id 582 NridgHt overpred) look like location/partial-sale residuals a linear member may catch.
- 3. Replace equal 1/3 weights with OOF-only (training-fold) non-negative weights for LGBM/XGB/CatBoost; never use the predict file. Equal weights may still overweight correlated trees after the feature change.
## Open questions
- Does the 0.00235 quick drop survive the hidden 293, or does Id 524 (if present) get the same 3× overprediction as Id 1299 and wipe it out?
- How much of fold 3’s −0.00669 is the row drop vs the new columns?
- Is QualGrLiv actually used by the trees, or is it collinear with OverallQual and GrLivArea already in the matrix?
