# Handoff n004: LGBM+XGB+CatBoost log-space blend
## Hypothesis
Keep TabularFeatures as-is. Fit three models on log1p(SalePrice) with the same train-only preprocessing: current LGBM (800/0.05/31), an XGBRegressor with similar conservative params (n_estimators=800, learning_rate=0.05, max_depth=4, subsample=0.8, colsample_bytree=0.8, seed=42), and CatBoostRegressor (iterations=800, learning_rate=0.05, depth=6, seed=42, verbose=0; pass the label-encoded cat columns as cat_features). Average the three log-space predictions then expm1 and clip as now. Equal weights; do not tune weights on the predict file.
## What I did
- Confirmed untouched parent quick RMSLE 0.12694 (same folds as n001).
- Replaced `LGBMLogModel` in `src/model.py` with `BlendLogModel`: LGBM params unchanged; added `XGB_PARAMS` and `CAT_PARAMS`; each model fits `log1p(y)`; predict is the mean of the three log preds, then expm1 and clip to `[0.5·ymin, 1.5·ymax]`. CatBoost gets the 22 label-encoded columns as `cat_features` after casting them to int32. All three use seed 42 and one thread; CatBoost `allow_writing_files=False`.
- Rewired `train.py` to `BlendLogModel`. `TabularFeatures` and the CLI (`--train/--predict/--out`, `Id,SalePrice`) unchanged.
- Smoke-checked CatBoost integer `cat_features` on an 800/367 split before the evaluator run.
## Result
- quick (untouched parent, this worktree): score 0.12694, folds=[0.12405, 0.13612, 0.11611, 0.11892, 0.13949], elapsed=11.3s. Command: `eval/eval.py --seedset quick`.
- quick (this node, blend): score 0.12053, folds=[0.11526, 0.12763, 0.10596, 0.11617, 0.13762], score_std=0.01097, score_sem=0.00491, n=1167, elapsed=61.7s. Same command. Delta vs parent quick: −0.00641. All five folds improved (fold 4, the 0.14 tail, only −0.00187).
- validation: not computed here (harness-only). Parent official validation was 0.1418.
- Final git commit: `97778e94aacfdd11fd1c8176085fffd299eba372`.
## Mechanism
The three GBDTs split mixed Ames fields differently (leaf growth vs depth-limited trees vs ordered cat handling), so averaging in log space cancels some of the per-model residual. That matches RMSLE (log1p error) and is why every quick fold moved down, not just the mean. The remaining 0.13762 fold is still a tail: complementary tree biases did not remove the hard houses (likely Edwards-area outliers / unusual quality–size combinations the parent already flagged). The mean drop (−0.00641) is smaller than parent fold std (0.00929), so treat it as a consistent but modest signal, not a 0.01-class leap.
## Dead ends
- Did not tune blend weights on the predict file (hypothesis forbade it). Equal 1/3 weights only.
- No per-model leave-one-out ablation on the quick folds, so it is unknown whether XGB or CatBoost is the main complement to LGBM.
- CatBoost integer `cat_features` wiring worked on the first try; not a dead end here.
## Next hypotheses
- 1. Add TotalBath, TotalPorchSF, and OverallQual×GrLivArea on top of this blend; drop zero-gain HasGarage/HasBsmt; exclude Edwards GrLivArea>4000 cheap sales from training. The 0.13762 fold barely moved; those are the classic Ames knobs for that tail.
- 2. Keep the three-tree blend and add a Ridge (or ElasticNet) on one-hot categoricals plus log-skewed area features as a fourth log-space member. n002’s linear model sat near 0.13 quick with different errors than trees.
- 3. Replace equal weights with OOF-only (training-fold) non-negative weights for LGBM/XGB/CatBoost; never use the predict file. Equal weights may overweight correlated trees.
## Open questions
- Does the 0.00641 quick drop survive the hidden 293-row holdout, or did three 800-tree models memorize the same 1167 rows?
- Which of LGBM/XGB/CatBoost is redundant under equal weights?
- Fold 4 is still ~0.02 worse than the best fold; is that Edwards GrLivArea>4000, or a neighborhood the label codes under-serve?
