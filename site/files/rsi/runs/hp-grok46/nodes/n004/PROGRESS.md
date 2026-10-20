# n004 progress

## Plan
Hypothesis: keep TabularFeatures; equal-weight LGBM + XGB + CatBoost blend in log space (expm1 + clip after mean of log preds).

## 2026-09-10 start
- Worktree is parent n001 (LGBMLogModel, 84 TabularFeatures cols).
- Parent reported quick RMSLE 0.12694 (folds 0.12405, 0.13612, 0.11611, 0.11892, 0.13949).
- Untouched quick: score 0.12694, folds=[0.12405, 0.13612, 0.11611, 0.11892, 0.13949], elapsed=11.3s. Matches n001.
- Implementing BlendLogModel: LGBM (unchanged params) + XGB (800/0.05/depth 4/subsample 0.8) + CatBoost (800/0.05/depth 6, label-encoded cats as cat_features). Equal log-space mean, then expm1+clip. n_jobs/thread_count=1.
- Smoke: 800/367 chronological split RMSLE 0.12203 in 14.5s; CatBoost accepted 22 int32 cat columns. Commit 97778e9.
- Running eval/eval.py --seedset quick.

## Quick result (blend)
- Command: `eval/eval.py --seedset quick --python <task .venv python>`
- score 0.12053, folds=[0.11526, 0.12763, 0.10596, 0.11617, 0.13762], score_std=0.01097, score_sem=0.00491, n=1167, elapsed=61.7s
- vs untouched parent quick 0.12694: Δ=−0.00641. All 5 folds improved.
- Fold-wise vs parent: 0.12405→0.11526, 0.13612→0.12763, 0.11611→0.10596, 0.11892→0.11617, 0.13949→0.13762. Tail fold 4 barely moved (−0.00187).
- Mean delta is smaller than parent fold std (0.00929); direction is consistent across folds.
- No catboost_info files written. Final commit 97778e94aacfdd11fd1c8176085fffd299eba372.
- Writing HANDOFF.md and proposals.json. Hypothesis complete; not tuning weights.

