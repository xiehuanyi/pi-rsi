# Progress n002: Wide regularized linear model

## Plan
Implement the assigned hypothesis only: expand the baseline ridge (8 numeric features, alpha=10, log1p target) with:
- integer maps for all ordinal quality/condition columns
- train-only one-hot of high-signal categoricals (Neighborhood, MSZoning, BldgType, HouseStyle, Foundation, GarageType, SaleCondition)
- train-median numeric imputation
- log1p of skewed area features (LotArea, GrLivArea, TotalBsmtSF, 1stFlrSF, GarageArea)
- TotalSF and bathroom/room totals
- Ridge or ElasticNetCV on StandardScaler, log1p(SalePrice), alpha grid ~1–100

## 2026-09-10 start
- Read TASK.md, README.md, train.py, src/features.py, src/model.py, eval/eval.py, docs/data_description.txt, HYPOTHESIS.md.
- Baseline is ridge on 8 numeric columns. Parent official validation RMSLE 0.18359.
- Next: run untouched quick seed set so we have a same-evaluator starting number, then implement features+model.

## 2026-09-10 baseline quick (before any code change)
Command: `~/pi-rsi/tasks/kaggle-house-prices/.venv/bin/python eval/eval.py --seedset quick --python ~/pi-rsi/tasks/kaggle-house-prices/.venv/bin/python`

Result (quick, untouched baseline): score=0.16778, fold_scores=[0.1461, 0.16809, 0.15892, 0.14038, 0.22542], score_std=0.0304, score_sem=0.0136, n=1167, elapsed_s=5.7
Parent official validation was 0.18359. Fold 5 (0.22542) dominates the mean; improvements need to beat this by more than fold noise (~0.03 std).

## 2026-09-10 implement wide linear features
Writing `src/features.py` (ordinal maps, train-only one-hot with rare-level bucket, median impute, log1p areas, TotalSF/TotalBath) and `src/model.py` (RidgeCV + StandardScaler on log1p target).
Smoke test on full public train: 110 features, all finite, predictions in ~45k–615k. GCV picked alpha=100 on the 1–100 grid (boundary), so the grid was widened to 1–1000; GCV then picked ~199.5.
About to run quick eval.

## 2026-09-10 wide ridge quick result
Command: same eval/eval.py --seedset quick as baseline.

Result (quick, wide RidgeCV): score=0.13125, fold_scores=[0.11296, 0.13245, 0.10657, 0.12831, 0.17596], score_std=0.0243, score_sem=0.01087, n=1167, elapsed_s=6.3
Baseline quick was 0.16778. Drop of 0.0365, larger than baseline fold std (0.0304) and new SEM (0.01087). Commit 40a8222.

## 2026-09-10 ElasticNetCV vs Ridge (local, same 5 folds as evaluator)
Ridge mean 0.13125; ElasticNetCV (l1_ratio grid, nested cv=5) mean 0.12966. Delta 0.0016 << fold std 0.024, treated as noise. Keep RidgeCV.
Fold 4 (0.17596) is dominated by Id 1299 (Edwards, GrLivArea=5642, TotalBsmtSF=6110, SalePrice=160000, ridge pred ~1.27e6). Outlier handling is a next-node idea, not this hypothesis.

No further in-hypothesis changes. Writing HANDOFF.md and proposals.json.

## 2026-09-10 done
HANDOFF.md and proposals.json written. Worktree clean at 40a8222fa116d5a6c2ccbedf4a392425e185411d.
quick: baseline 0.16778 -> wide ridge 0.13125. Hypothesis confirmed on the quick seed set.
