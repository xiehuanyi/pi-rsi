# n007 progress

## Plan
Hypothesis: on n001 LGBM, add TotalBath, TotalPorchSF, QualArea=OverallQual*GrLivArea; drop HasGarage/HasBsmt (0 split gain); drop train rows with GrLivArea>4000 and SalePrice<300000. Predict file unfiltered. Same LGBMLogModel and CLI.

Note: n005 ran a similar bundle on the n004 blend; official validation got worse (0.14524 vs 0.1389) because cheap palaces remaining as *prediction* targets are still ~3× overpredicted. This node tests the same idea on the LGBM parent.

## 2026-09-10 start
- Read train.py, src/features.py, src/model.py, TASK.md, HYPOTHESIS.md, n001/n005 handoffs.
- Current code is n001 LGBM + TabularFeatures (84 cols, HasGarage/HasBsmt present).

## Untouched parent quick
- Command: `eval/eval.py --seedset quick`
- quick: score 0.12694, folds=[0.12405, 0.13612, 0.11611, 0.11892, 0.13949], elapsed=10.4s, n=1167.
- Matches n001 handoff exactly.

## Data note
- Public train cheap palace: Id 1299 Edwards GrLivArea=5642 SalePrice=160000. Dropped from fit.
- Id 1183 NoRidge 4476/745000 is kept (not cheap).
- The other classic Edwards palace (Id 524) is not in public train.

## Implementation
- `src/features.py`: `add_engineered` now emits TotalBath, TotalPorchSF, QualArea; no longer emits HasGarage/HasBsmt. Added `drop_train_outliers` (GrLivArea>4000 and SalePrice<300000). Missing addends filled with 0 after train-coerced numerics.
- `train.py`: drop outliers on the labeled train frame only, then same `TabularFeatures` + `LGBMLogModel`. Predict file is never filtered.
- Smoke: 1167→1166 (only Id 1299); 85 features; extras present; flags gone; test transform 1459 rows; CLI `Id,SalePrice` ok. In-sample-except-1299 pred for Id 1299 is ~463659 vs 160000 (~2.90×).

## About to run
- quick eval of this node (same command). Fold that holds Id 1299 as val still *evaluates* it; drop only affects training.

## After quick eval (this node)
- Command: `eval/eval.py --seedset quick`
- quick: score 0.12460, folds=[0.11906, 0.13459, 0.12197, 0.11501, 0.13235], score_std=0.00761, score_sem=0.0034, n=1167, elapsed=10.7s.
- vs parent 0.12694 / [0.12405, 0.13612, 0.11611, 0.11892, 0.13949]. Delta mean −0.00234. Per-fold: −0.00499, −0.00153, +0.00586, −0.00391, −0.00714.
- 4/5 folds down. Fold 2 worse. Fold 4 (contains Id 1299 as val) 0.13949 → 0.13235. Mean delta (0.00234) ≪ parent fold std 0.00929.
- Commit: 8ee1ac422e5e99c4c7a4379c9baf568c6b68f3cb

## Fold-4 residual diagnostic (not an official score)
- This node, fold 4: Id 1299 pred 467199 vs true 160000 (~2.92×). Fold-4 RMSLE without 1299 = 0.11244 (vs 0.13235 with it).
- Parent fold 4: Id 1299 pred 485928 (~3.04×). Fold-4 RMSLE without 1299 = 0.11926.
- Id 1299 is val in fold 4, so the train drop never touches that fit. Fold 4’s −0.00714 is extras-only (TotalBath/TotalPorchSF/QualArea, flags dropped).
- Full-public-train (after drop) LightGBM split gain: TotalSF 1393, QualArea 1365, TotalPorchSF 1085, TotalBath 293. QualArea is used, not ignored.

## Decision
Ship the hypothesis as specified. Mean quick move is inside fold noise. n005 already showed this train-drop can hurt official if a twin cheap palace is in the 293. Next node should ablate the row drop vs extras, or cap area on both train and predict instead of dropping rows.
