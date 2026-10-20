# Progress n008

## Plan
Hypothesis: keep equal-weight LGBM+XGB+CatBoost+Ridge log-space blend and tree params. Robustify only the Ridge member: winsorize/cap GrLivArea, TotalBsmtSF, 1stFlrSF, TotalSF at a train-fitted statistic (99th percentile or 4000 sqft) on both train and predict linear features, and/or drop Edwards / cheap GrLivArea>4000 palaces from the Ridge fit only. Trees still train on the full labeled frame. Goal: keep folds 0–3 Ridge gain without the fold-4 ridge 0.16959 blow-up.

## 2026-09-10 start
- Worktree is n006 4-way blend at `89282eb`.
- Public train n=1167. Id 1299 Edwards GrLivArea=5642 TotalBsmtSF=6110 1stFlrSF=4692 TotalSF=11752 SalePrice=160000 is present. Id 524 (the twin cheap palace) is not. Id 1183 NoRidge 4476/745000 is a real luxury sale.
- Percentiles on public train: GrLivArea p99≈3083 max 5642 (2 rows >4000); TotalBsmtSF p99≈2155 max 6110 (1 >4000); 1stFlrSF p99≈2227 max 4692 (1 >4000); TotalSF p99≈4843 max 11752 (54 rows >4000). A raw 4000 cap on TotalSF would flatten 54 houses; a raw 99th cap on GrLivArea would flatten 12 houses including several real NoRidge palaces.
- Intended implementation (after parent quick): cap living-area fields at max(4000, train 99th) so only the extreme tail is clipped; drop cheap palaces (GrLivArea>4000 and (Edwards or SalePrice<300k)) from Ridge fit only.
- Next: untouched parent quick eval.

## Untouched parent quick (before edits)
Command: `eval/eval.py --seedset quick` with task venv python.
Result: score=0.11896, folds=[0.10991, 0.12521, 0.10227, 0.1139, 0.14352], n=1167, elapsed=60.7s.
Matches n006 worker quick exactly. Baseline for this node.

## Implementation
Ridge-only robustification, trees unchanged:
- `LinearRidgeFeatures`: cap GrLivArea, TotalBsmtSF, 1stFlrSF, TotalSF at the train 99th percentile on train and predict. BsmtFinSF1 is clipped to the TotalBsmtSF cap so the finished-basement column cannot exceed the capped total.
- `ridge_keep_mask`: drop Edwards GrLivArea>4000 or (GrLivArea>4000 and SalePrice<300k) from Ridge fit only.
- `BlendLogModel.fit(..., ridge_keep=)`: trees still see every labeled row.
- Caps/medians/one-hots still fit on the full labeled train frame.

## Ridge-only diagnostic (same RandomState(20260910) folds, not evaluator)
Parent ridge: folds [0.11296, 0.13245, 0.10657, 0.12831, 0.16959] mean 0.12998. Id 1299 pred 1.12e6 (clip bound). Id 1183 pred 273k vs 745k.
Cap at max(4000, p99) only: fold 4 0.16803, Id 1299 still 1.08e6. Named living-area caps are not the lever; BsmtFinSF1=5644 is the top log-price contribution (+0.53).
Drop only: mean 0.12244, fold 4 unchanged 0.16959. Folds 1 and 3 improved; Id 1183 472k.
Cap 4000-floor + drop: mean 0.12271, fold 4 0.16803.
Pure 99th + drop: mean 0.12240, fold 4 0.16405, Id 1299 996k.
99th + drop + BsmtFinSF1 p99 (diagnostic, extra): fold 4 0.14608, Id 1299 668k.
99th + drop + BsmtFinSF1/LotArea/LotFrontage (diagnostic, extra): fold 4 0.14159, Id 1299 596k.

Chose train-99th on the named four + BsmtFinSF1 clipped to the TotalBsmtSF cap + palace drop. That stays inside "cap TotalBsmtSF" while actually cutting the 5644 finished-basement spike.

Final ridge-only (this code): folds [0.11677, 0.12253, 0.10194, 0.10672, 0.14787] mean 0.11917 std 0.01608. Fold 4 0.16959→0.14787. Id 1299 pred 697k (4.36× vs parent 6.98×). Id 1183 414k (0.56× vs parent 0.37×).

Smoke CLI: `train.py --train data/train.csv --predict data/test.csv` wrote 1459 rows Id,SalePrice, no NaN/inf, ids match test, prices in [50133, 519075]. Files under 400 lines.

## Commit
`30dc164` Robustify Ridge with train-99th area caps and palace-row drop.

## Quick eval (this node)
Command: `eval/eval.py --seedset quick` with task venv python.
Result: score=0.11638, folds=[0.11172, 0.12262, 0.10076, 0.10958, 0.13721], score_std=0.01253, score_sem=0.0056, n=1167, elapsed=62.2s.
vs parent quick 0.11896: Δ=−0.00258.
Per-fold Δ: +0.00181, −0.00259, −0.00151, −0.00432, −0.00631.
Fold 4 0.14352→0.13721 (the n006 blow-up is gone; slightly below the 3-tree parent fold 4 of 0.13762). Fold std 0.01434→0.01253.
Fold 0 is the only regression (typical-house fold; 1299 is in that train split and is dropped from Ridge).
Mean Δ is still below fold std (0.01253); treat as a modest consistent signal, not a 0.01-class leap.

## Side diagnostic (same folds, not evaluator)
Fold 4 member RMSLE: lgbm=0.13949, xgb=0.14416, cat=0.14066, ridge=0.14787, blend=0.13721.
Id 1299: lgbm 485928, xgb 637352, cat 551087, ridge 697220, blend 587334 vs 160000 (ridge was 1.12e6 parent).
Id 1183: ridge 414402, blend 370250 vs 745000 (ridge was 272505 parent).

## Conclusion
Hypothesis implemented. Named living-area caps at 4000 were not enough (BsmtFinSF1=5644 dominated); clipping BsmtFinSF1 to the TotalBsmtSF 99th made the cap real. Palace drop helped folds 1–3 and Id 1183. Trees still ~3–4× overpredict 1299; the blend gain is Ridge no longer voting a million-dollar palace. Write handoff.
