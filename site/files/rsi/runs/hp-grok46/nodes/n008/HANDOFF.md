# Handoff n008: Robustify Ridge areas / Edwards
## Hypothesis
Keep the equal-weight LGBM+XGB+CatBoost+Ridge log-space blend and tree params. Change only the Ridge member: winsorize/cap GrLivArea, TotalBsmtSF, 1stFlrSF, and TotalSF at a statistic fit on the labeled train frame (99th percentile or 4000 sqft) for both train and predict linear features, and/or drop Edwards rows with GrLivArea>4000 (or SalePrice<300000 and GrLivArea>4000) from the Ridge fit only. Trees still train on the full labeled frame. Goal is to keep the folds 0–3 Ridge gain without the fold-4 ridge 0.16959 blow-up.
## What I did
- Confirmed untouched parent quick RMSLE 0.11896 (same folds as n006).
- Public train still has Id 1299 (Edwards, GrLivArea=5642, TotalBsmtSF=6110, BsmtFinSF1=5644, SalePrice=160000) in quick fold 4 and Id 1183 (NoRidge, 4476/745000) in fold 3. Id 524 is not in public train.
- `src/linear_features.py`: `LinearRidgeFeatures` caps GrLivArea, TotalBsmtSF, 1stFlrSF, and TotalSF at the labeled-train 99th on train and predict. BsmtFinSF1 is clipped to the TotalBsmtSF cap so finished basement cannot exceed the capped total. Added `ridge_keep_mask` (Edwards GrLivArea>4000 or GrLivArea>4000 with SalePrice<300k). Medians/one-hots/caps still fit on the full labeled train frame.
- `src/model.py` `BlendLogModel.fit`: trees still see every labeled row; Ridge fits only `ridge_keep` rows. Tree params and equal 1/4 log average unchanged.
- `train.py` passes `ridge_keep_mask(train)` into the blend.
- Ridge-only ablations on the same `RandomState(20260910)` folds (not the evaluator) chose 99th over a 4000 floor: a 4000 living-area cap left Id 1299 at ~1.08e6 because BsmtFinSF1=5644 was the top log-price contribution (+0.53).
## Result
- quick (untouched parent, this worktree): score 0.11896, folds=[0.10991, 0.12521, 0.10227, 0.1139, 0.14352], score_std=0.01434, score_sem=0.00641, n=1167, elapsed=60.7s. Command: `eval/eval.py --seedset quick`.
- quick (this node): score 0.11638, folds=[0.11172, 0.12262, 0.10076, 0.10958, 0.13721], score_std=0.01253, score_sem=0.0056, n=1167, elapsed=62.2s. Same command. Delta vs parent quick: −0.00258.
- Per-fold Δ: +0.00181, −0.00259, −0.00151, −0.00432, −0.00631. Fold 4 0.14352→0.13721 (n006’s blow-up is gone; 0.13721 is slightly below the 3-tree parent fold 4 of 0.13762). Fold std 0.01434→0.01253. Fold 0 is the only regression.
- Mean drop is still below fold std (0.01253); this is a modest consistent signal, not a 0.01-class leap.
- Side diagnostic (same folds, not evaluator): ridge-only parent [0.11296, 0.13245, 0.10657, 0.12831, 0.16959] mean 0.12998 → this [0.11677, 0.12253, 0.10194, 0.10672, 0.14787] mean 0.11917. Fold 4 member RMSLE lgbm=0.13949, xgb=0.14416, cat=0.14066, ridge=0.14787, blend=0.13721. Id 1299 preds: lgbm 485928, xgb 637352, cat 551087, ridge 697220, blend 587334 vs 160000 (parent ridge was 1.12e6). Id 1183: ridge 414402, blend 370250 vs 745000 (parent ridge 272505).
- validation: not computed here (harness-only). Parent official validation was 0.1369.
- Final git commit: `30dc16428c9ad3bcc3535b42dac5585b71b06405`.
## Mechanism
Ridge’s fold-4 disaster was leverage, not missing neighborhood dummies. Id 1299 is Qual=10 / 2008 / Partial with GrLivArea=5642 and BsmtFinSF1=5644; unclipped, Ridge hits the 1.5·ymax clip (~1.12e6). Capping the four named size fields at 4000 barely moved that prediction, because the finished-basement column still scored +0.53 log-price. Clipping BsmtFinSF1 to the train-99th TotalBsmtSF cap makes the basement cap real (ridge 1299 → 697k, fold-4 ridge 0.16959→0.14787). Dropping the cheap palace from the Ridge fit (not the trees) stops it from pulling coefficients when it is in the train split, which is why folds 1–3 and the genuine NoRidge palace (Id 1183 272k→414k) improve. Trees still ~3–4× overpredict 1299 (blend 587k); the blend win is that Ridge no longer casts a million-dollar vote. Equal 1/4 is now additive on fold 4 instead of toxic. The same predict-time cap is the holdout protection n005 lacked: Id 524, if present, will also see clipped areas even though it is never dropped from a training frame.
## Dead ends
- Cap at 4000 sqft (or max(4000, 99th)) on GrLivArea/TotalBsmtSF/1stFlrSF/TotalSF without touching BsmtFinSF1: fold-4 ridge 0.16803, Id 1299 still ~1.08e6. The named living-area caps are not the lever.
- Drop-only (no cap): ridge mean 0.12244 but fold 4 stays 0.16959 and Id 1299 stays 1.12e6. Same n005 failure mode if a twin palace is a prediction target.
- Pure 99th on the four named columns without the BsmtFinSF1 consistency clip: fold-4 ridge 0.16405, Id 1299 still 996k. Not enough.
- Did not retune tree params or blend weights (hypothesis forbade both).
## Next hypotheses
- 1. Keep this 4-way blend, 99th caps, and Ridge-only palace drop. Also winsorize LotArea and LotFrontage at the labeled-train 99th on the Ridge matrix only (Id 1299 is 63887 / 313 vs fold-4 train p99 ~34000 / 139; they were the next log-price contributions after BsmtFinSF1). Trees unchanged.
- 2. Replace equal 1/4 with OOF-only non-negative weights (sum to 1) on the four log-space members, fit inside the labeled train file. Ridge is no longer a fold-4 bomb (0.14787 vs 0.16959), so NNLS may keep a useful Ridge weight instead of shrinking it to 0.
- 3. Ablate the Ridge-only row drop: keep the 99th area caps + BsmtFinSF1 clip, but fit Ridge on every labeled row. If quick fold 4 stays near 0.137 and only folds 1/3 give back their drop-driven gains, the cap is the holdout-safe piece (n005’s train-only drop hurt official 0.14524).
## Open questions
- Does the hidden 293 still hold Id 524? The predict-time 99th cap should clip it; n005’s train-only drop could not.
- Id 1299 is still a 3.7× blend overprediction (587k vs 160k). Is that one row still most of fold 4’s 0.13721, and will a similar holdout row dominate official RMSLE?
- Fold 0 got slightly worse (0.10991→0.11172) when 1299 is dropped from the Ridge train split. Is that noise, or does the drop hurt typical-house coefficients?
- 99th GrLivArea (~3100) flattens Id 1183 (4476/745000) to a 414k Ridge pred; is that an acceptable luxury bias versus the 4000-sqft floor that failed to tame 1299?
