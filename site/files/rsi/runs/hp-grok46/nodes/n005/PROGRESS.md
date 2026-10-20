# n005 progress

## Plan
Hypothesis: Ames extras (TotalBath, TotalPorchSF, OverallQual*GrLivArea) + drop HasGarage/HasBsmt + drop Edwards GrLivArea>4000 cheap sales. Keep BlendLogModel.

## 2026-09-10 start
- Read train.py, src/features.py, src/model.py, TASK.md, HYPOTHESIS.md.
- BlendLogModel + TabularFeatures unchanged from n004 (commit 97778e94).

## Untouched parent quick
- Command: `eval/eval.py --seedset quick`
- quick: score 0.12053, folds=[0.11526, 0.12763, 0.10596, 0.11617, 0.13762], elapsed=62.1s, n=1167.
- Matches n004 handoff exactly.

## Data note
- Public train has one cheap palace: Id 1299, Edwards, GrLivArea=5642, SalePrice=160000. In quick fold 4 (the 0.13762 tail).
- Id 1183 NoRidge 4476 / 745000 is kept (not Edwards, not cheap).
- The other classic Edwards palace (Id 524) is not in public train; likely in the hidden 293.

## Implementation
- `src/features.py`: add TotalBath, TotalPorchSF, QualGrLiv; remove HasGarage/HasBsmt; `drop_train_outliers` for Edwards|cheap GrLivArea>4000.
- `train.py`: drop outliers on labeled train only, then same BlendLogModel + clip.
- Smoke: drop only Id 1299 (1167→1166); 85 features; extras present; flags gone; test transform keeps 1459 rows.

## About to run
- quick eval of this node (same command). Fold 4 still *evaluates* Id 1299 (cannot drop from predict); drop only affects folds 0–3 training. Fold 4 change is feature-only.

## After quick eval (this node)
- Command: `eval/eval.py --seedset quick`
- quick: score 0.11818, folds=[0.11371, 0.12694, 0.10627, 0.10948, 0.13452], score_std=0.01078, score_sem=0.00482, n=1167, elapsed=62.5s.
- vs parent 0.12053 / [0.11526, 0.12763, 0.10596, 0.11617, 0.13762]. Delta mean −0.00235. Per-fold: −0.00155, −0.00069, +0.00031, −0.00669, −0.00310.
- 4/5 folds down. Fold 4 (target tail, contains Id 1299 as val) 0.13762 → 0.13452. Fold 3 largest gain (contains genuine NoRidge palace Id 1183 as val).
- Mean delta (0.00235) < fold std (~0.011); treat as modest consistent signal, not a 0.01-class leap.
- Commit: 5253670acd7a9835f69f6495b23b53f93d828ef0

## Fold-4 residual diagnostic (not an official score)
- This node, fold 4: Id 1299 pred 536995 vs true 160000, log sqerr 1.466. Fold-4 RMSLE without 1299 = 0.10887 (vs 0.13452 with it).
- Parent fold 4: Id 1299 pred 554699, sqerr 1.546. Fold-4 RMSLE without 1299 = 0.11117.
- So extras slightly *helped* the rest of fold 4; QualGrLiv did not make 1299 worse. The palace is still ~3.4× overpredicted because nothing in train looks like a cheap 5642 sqft house.
- If hidden holdout contains the other Edwards palace (Id 524), dropping 1299 from train will overpredict it the same way and can *hurt* official validation even though quick improved.

## Decision
Ship the hypothesis as specified. No extra model-family changes. Next node should ablate the row drop vs extras, and/or add a complementary linear blend member.
