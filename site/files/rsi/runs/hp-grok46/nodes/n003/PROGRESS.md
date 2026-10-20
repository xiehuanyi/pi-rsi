# n003 progress

## Hypothesis
CatBoostRegressor with native categoricals (object/string columns + MSSubClass), log1p target, minimal FE (numeric median fill, cat NA → 'Missing', TotalSF, house Age). iterations≈1000, depth≈6, lr≈0.05, l2_leaf_reg≈3, fixed seed.

## 2026-09-10 start
- Worktree is root baseline: ridge on 8 numeric features.
- Parent official validation: 0.18359.
- n001 LightGBM (different hypothesis) quick 0.12694, official 0.1418.
- Next: measure untouched ridge on quick, then implement CatBoost only.

## 2026-09-10 baseline (untouched ridge)
- Command: `eval/eval.py --seedset quick`
- quick: score 0.16778, folds=[0.1461, 0.16809, 0.15892, 0.14038, 0.22542], n=1167, elapsed=5.8s
- Matches n001's untouched ridge number.

## 2026-09-10 implementing CatBoost
- `src/features.py`: CatBoostFrameBuilder — train-only numeric medians, cat NA→Missing, MSSubClass as cat, TotalSF, Age.
- `src/model.py`: CatBoostLogModel — log1p/expm1, 1000/6/0.05/3, seed 42, 12% internal holdout for early stopping then refit on full train.
- `train.py` rewired. CLI unchanged.
- Smoke (full public train → test): 37 numeric + 44 cat, 0 NAs, n_iter=723, pred [52832, 157302, 555681], 32.5s.
- Commit: CatBoost implementation. Next: quick 5-fold.

## 2026-09-10 CatBoost first quick eval
- Starting `eval/eval.py --seedset quick` (5 trainings, each ~probe+refit).
- Result: score 0.12187, folds=[0.11096, 0.1298, 0.10497, 0.1209, 0.14271], score_std=0.01344, score_sem=0.00601, n=1167, elapsed=107.4s.
- Delta vs ridge quick 0.16778: −0.04591. Better than n001 LightGBM quick 0.12694 on the same seed set.
- Fold std 0.01344; this drop is far above noise. No further change — hypothesis is implemented as specified.
- Final commit: 9f9b98359d7ce9f8e7c7bc39faa68f0dfe60e378
- Next: HANDOFF.md + proposals.json. Do not bundle extra FE or a second model in this node.
