# Progress n001: LightGBM on full tabular features with ordinal/NA handling

## Plan
Replace 8-feature ridge with LightGBMRegressor on log1p(SalePrice), using nearly all columns:
- ordinal quality cols as ordered ints (NA→0)
- numeric NA filled with train medians
- remaining categoricals label-encoded on train only with UNK bucket
- cheap engineered fields: TotalSF, Age, RemodAge, HasGarage, HasBsmt
- conservative LGBM params: n_estimators≈800, lr≈0.05, num_leaves≈31, min_child_samples≈20, subsample/colsample≈0.8
- clip predictions to a sane positive range

## 2026-09-10 start
Working directory is the n001 worktree. Parent/root official validation RMSLE is 0.1836 (ridge on 8 numeric features).
Train shape: 1167 x 81. 43 object cols, 38 numeric. Heavy NA: PoolQC/MiscFeature/Alley/Fence/MasVnrType/FireplaceQu/LotFrontage/garage block/bsmt block.
SalePrice min 34900 max 745000.

## Before eval: untouched baseline (ridge, 8 numeric features)
Command: eval/eval.py --seedset quick
Expect ~0.18 RMSLE. Need this as the starting-point number for this node.

## After baseline quick
quick RMSLE = 0.16778 (n=1167, folds=[0.1461, 0.16809, 0.15892, 0.14038, 0.22542], elapsed=5.5s).
Parent official validation was 0.18359. Fold 4 is an outlier (0.225).

## Implementation
Replaced 8-feature ridge with:
- `src/features.py`: TabularFeatures — ordinal quality maps (NA→0), train medians for numerics, label-encode remaining cats with UNK, engineered TotalSF/Age/RemodAge/HasGarage/HasBsmt. 84 features (40 num + 22 ord + 22 cat).
- `src/model.py`: LGBMLogModel on log1p(SalePrice), n_estimators=800, lr=0.05, num_leaves=31, min_child_samples=20, subsample/colsample=0.8, subsample_freq=1, seeds=42, n_jobs=1. Clip to [0.5*ymin, 1.5*ymax].
- `train.py` wires them; CLI unchanged.
Smoke (first 50 rows as val, rest train): RMSLE 0.0897, no NaNs, ~2s.

## Before eval: LightGBM full features
Command: eval/eval.py --seedset quick
Expect ~0.12–0.14 if the hypothesis holds.

## After LightGBM quick
quick RMSLE = 0.12694 (n=1167, folds=[0.12405, 0.13612, 0.11611, 0.11892, 0.13949], score_std=0.00929, score_sem=0.00416, elapsed=10.8s).
Delta vs untouched ridge quick 0.16778: −0.04084. All five folds improved; fold spread is much tighter (baseline fold 4 was 0.22542, now 0.13949).
Hypothesis confirmed on the quick seed set. No further changes in this node (one hypothesis).

Kaggle-path smoke: `train.py --train data/train.csv --predict data/test.csv` writes 1459 finite Id,SalePrice rows (min≈51689, max≈526185).
Split importances (full public train): TotalSF 1688 (top), RemodAge 714, Age 622; HasGarage=0 and HasBsmt=0 (redundant with GarageArea/TotalBsmtSF for trees).

Final commit: 7549b29c8cbc8dcbcd27c4b4027a656ee579e96b Replace 8-feature ridge with LightGBM on full tabular features.

## Handoff written
HANDOFF.md and proposals.json are in this node notes directory. No further code changes. Node complete.
