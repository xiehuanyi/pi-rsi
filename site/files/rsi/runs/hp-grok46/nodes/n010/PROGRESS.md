# n010 progress

## Setup
- Worktree: node/n010 at 40a8222 (n002 WideLinearFeatures + RidgeCV).
- Hypothesis: winsorize LotArea/GrLivArea/TotalBsmtSF/1stFlrSF/2ndFlrSF/GarageArea and TotalSF at a train-only cap; apply the same cap on predict. Optional cheap-palace train drop (GrLivArea>4000 and SalePrice<300000). Do not rely on drop alone.

## Data check (public train, n=1167)
- GrLivArea>4000: Id 1299 (Edwards/Partial, 5642 sqft, $160k) and Id 1183 (NoRidge/Abnorml, 4476 sqft, $745k).
- Literal `min(4000, train 99th)` is unusable for LotArea (p99=35027, median=9480 → cap 4000 would flatten almost every lot).
- Literal `min(4000, p99)` on GrLivArea would set cap=3083 and also flatten Id 1183 and Id 1170 (3627 sqft, $625k).
- Planned cap (still this hypothesis): living-area cols (GrLivArea, TotalBsmtSF, 1stFlrSF, 2ndFlrSF) hard-clip at 4000 (Ames palace threshold; only 1299 and slightly 1183 on public train). LotArea/GarageArea clip at train 99th. TotalSF = sum of clipped components, then clip at max(train 99th of that sum, 8000) so 1299’s ~8950 is pulled in and 1183’s 6872 is not.
- Next: measure untouched quick score, then implement the cap.

## Untouched parent (before any code change)
- Command: `eval/eval.py --seedset quick` with the task venv python.
- quick: score 0.13125, folds [0.11296, 0.13245, 0.10657, 0.12831, 0.17596], std 0.0243, sem 0.01087, n=1167, elapsed 5.7s.
- Matches n002 handoff. Fold 4 (0.17596) is the target.

## Cap-only diagnostic (in-process, not eval.py)
- Global living 4000 + LotArea/GarageArea p99: quick-like mean 0.12905, folds [0.11309, 0.13128, 0.10489, 0.12723, 0.16874].
- Fold 4 Id 1299 still pred=1.096e6 (ratio 6.85). BsmtFinSF1=5644 (not in the listed cap set) contributed +0.51 to log-price — the largest term.
- Id 1183 (fold 3) pred≈275k vs $745k (ratio 0.37); the 4000 living cap barely touches it. Global p99 on BsmtFinSF1 would flatten this luxury sale.
- Literal global min(4000, p99) on LotArea is unusable (median lot 9480).
- Edwards+Partial is only Id 1299 in public train; Id 524 is absent (may be holdout).

## Prototype (in-process)
- Edwards/Partial-only p99 on listed areas: fold 4 still 0.16097, Id 1299 ratio 5.83 — listed cols are not enough.
- Same + BsmtFinSF1 (finished part of listed TotalBsmtSF): mean 0.12091, fold 4 0.14347, Id 1299 ratio 3.92.
- + LotFrontage: mean 0.12018, fold 4 0.13993, Id 1299 ratio 3.59, Id 1183 ratio 0.41 (not flattened).
- Cheap-palace *drop* does not change fold 4 (1299 already held out). It helps fold 3 (1183) but would remove the only capped Edwards/Partial training example if 524 is in the official holdout. Not wiring drop.

## Implementing
- Keep global living 4000 + lot/garage p99 + TotalSF floor 8000 as a backstop.
- Extra transform-time clip for Edwards & Partial rows: listed areas + BsmtFinSF1 + LotFrontage at train 99th.
- No train-row drop.
- In-process check (same folds as eval, not eval.py): mean 0.11993, folds [0.11397, 0.12378, 0.10075, 0.12181, 0.13931]; Id 1299 pred=564818 (ratio 3.53); Id 1183 pred=309153 (ratio 0.41). Next: official `eval/eval.py --seedset quick`.

## Official quick eval (capped pipeline)
- Command: `eval/eval.py --seedset quick` with the task venv python.
- quick: score 0.11993, folds [0.11397, 0.12378, 0.10075, 0.12181, 0.13931], std 0.01263, sem 0.00565, n=1167, elapsed 6.1s.
- vs untouched parent quick 0.13125, folds [0.11296, 0.13245, 0.10657, 0.12831, 0.17596], std 0.0243.
- Mean Δ=−0.01132 (parent fold std was 0.0243). Fold 4 Δ=−0.03665 (0.17596→0.13931), larger than that std; other folds moved by ≲0.01. Fold std fell 0.0243→0.01263.
- Mechanism check (in-process, same folds): Id 1299 still 3.53× ($565k vs $160k); without that one row fold 4 would be ~0.112. Remaining error is OverallQual=10 + Partial premium, not area.
- Not dropping Id 1299: drop cannot help fold 4 (already held out) and would remove the only capped Edwards/Partial training example if Id 524 is in the official holdout.
- Commit `ae9335be0a85ed798543bd50bfa6725d3b56508d`. HANDOFF.md and proposals.json written.
