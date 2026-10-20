# Progress n006

## Plan
Hypothesis: keep equal-weight LGBM+XGB+CatBoost log-space blend; add Ridge (alpha grid 1–1000) on one-hot categoricals + log1p skewed areas as a fourth log-space member; average four log preds then expm1+clip. Linear pipeline fit on labeled train only. Do not retune tree params.

## 2026-09-10 start
- Worktree is clean at `97778e9` (n004 BlendLogModel).
- `src/model.py` is 3-way GBDT blend; `src/features.py` is TabularFeatures (label-encoded cats).
- n002 Ridge used WideLinearFeatures (ordinals, 7 one-hots, log areas, TotalSF/TotalBath) + StandardScaler + RidgeCV logspace(0,3,31); quick 0.13125.
- n005 is already taking the Edwards/TotalBath feature path, so this node stays on the Ridge-as-4th-member idea only.
- Next: untouched parent quick eval, then implement.

## Untouched parent quick (before edits)
Command: `eval/eval.py --seedset quick` with task venv python.
Result: score=0.12053, folds=[0.11526, 0.12763, 0.10596, 0.11617, 0.13762], score_std=0.01097, score_sem=0.00491, n=1167, elapsed=61.4s.
Matches n004 worker quick exactly. Baseline for this node.

## Implementation
Port n002 `WideLinearFeatures` (ordinals, 7 train-only one-hots with min-count-5 Other, log1p areas, TotalSF/TotalBath, variance mask) as `LinearRidgeFeatures`. Add StandardScaler+RidgeCV (alphas logspace(0,3,31)) as a fourth log-space member. Equal 1/4 average of LGBM+XGB+CatBoost+Ridge log preds, then expm1+clip. Tree params unchanged. Linear stats fit on the labeled train frame only.

Smoke (800/367 split, not the evaluator): tree (800, 84), lin (800, 108) no NaN; ridge alpha=79.43; split RMSLE 0.12289; one fit 12.45s. CLI `train.py --train data/train.csv --predict data/test.csv` wrote 1459 rows Id,SalePrice, no NaN.

Next: commit, then `eval/eval.py --seedset quick`.

## Commit
`89282eb` Add Ridge as fourth log-space blend member.

## Quick eval (this node)
Command: `eval/eval.py --seedset quick` with task venv python.
Result: score=0.11896, folds=[0.10991, 0.12521, 0.10227, 0.1139, 0.14352], score_std=0.01434, score_sem=0.00641, n=1167, elapsed=65.3s.
vs parent quick 0.12053: Δ=−0.00157.
Folds 0–3 all down (Δ −0.00535, −0.00242, −0.00369, −0.00227); fold 4 up +0.00590 (0.13762 → 0.14352).
Mean gain ≪ parent fold std 0.01097; score_std rose 0.01097 → 0.01434 because the tail fold got worse.

## Side diagnostic (same RandomState(20260910) folds, not evaluator)
Per-member mean RMSLE: lgbm=0.12694, xgb=0.12636, cat=0.12062, ridge=0.12998, tree3=0.12053, all4=0.11896.
Ridge folds 0–3 match n002 exactly [0.11296, 0.13245, 0.10657, 0.12831]; fold 4 0.16959 vs n002 0.17596 (this blend clips to 1.5·ymax).
Log-residual corr(tree3, ridge): [0.78, 0.853, 0.811, 0.774, 0.882], mean 0.82.
Ridge alphas: [251.19, 251.19, 251.19, 316.23, 63.1].
Fold 4: ridge 0.16959 vs tree3 0.13762 → all4 0.14352. Equal 1/4 lets the linear tail error vote.

## Conclusion
Hypothesis implemented as specified. Modest mean drop, below fold noise, with a clear tradeoff (typical houses vs Edwards-style tail). Do not retune; write handoff.
