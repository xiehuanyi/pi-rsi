# n009 progress

## Plan
Hypothesis: after spend>0 forces CryoSleep=False, fill remaining CryoSleep NA as True when total amenity spend is 0; add luxury share (Spa+VRDeck)/TotalSpend and food/shopping share (FoodCourt+ShoppingMall)/TotalSpend (0 when total is 0). Keep LightGBM.

1. Measure untouched n004 parent on quick seed set.
2. Probe CryoSleep NA vs spend on data/train.csv to confirm the domain rule and the awake-zero-spend exception.
3. Implement only those two changes in `src/features.py`.
4. Re-run quick eval; treat fold-std (~0.008) as noise floor.

## 2026-09-10 start
Working from parent n004 (official 0.8137, worker quick 0.80732). Code already forces CryoSleep=False when total spend > 0; remaining CryoSleep is left NA. Spend features are log1p of each amenity plus log_TotalSpend; no spend mix shares.

About to run untouched parent quick eval.

## Untouched parent (quick)
- Command: `.venv python eval/eval.py --seedset quick`
- score **0.80732** folds [0.79702, 0.81232, 0.81988, 0.80638, 0.80101] n=6954 elapsed=11.8s
- Matches n004 worker quick.

## Probe on data/train.csv (n=6954)
- CryoSleep NA: 186. After spend>0 → False: 100 rows. Remaining NA with total==0: **86** (77 all spends known 0; 9 some spend NA filled as 0).
- Cryo True never has spend>0. Cryo False with total==0: 416 (awake non-spenders exist).
- Transport rate: Cryo True 0.810; Cryo False 0.325; Cryo NA total>0 0.300; Cryo NA total==0 **0.709**; Cryo False total==0 0.596. Zero-spend NA looks more like cryo than awake, but ~25/86 would be mislabeled if all True.
- Among spenders (n=4030): luxury share corr with Transported **-0.329**; food/shopping share **+0.504**. Luxury mean by planet: Europa 0.49, Earth 0.40, Mars 0.14.

Implementing cryo NA→True at zero spend plus LuxuryShare and FoodShoppingShare. Keep LightGBM and log1p spends.

## Implementation
- `src/features.py`: `impute_cryosleep` (spend>0 → False; remaining NA and total==0 → True). `spend_mix_shares` adds LuxuryShare and FoodShoppingShare (0 if total==0).
- Sanity: CryoSleep NA 186 → 0 (False 4446 = 4346+100, True 2508 = 2422+86). Shares in [0,1], 0 when total==0. `train.py` writes 4277 predictions.
- Commit then run quick eval.

## Shipped hypothesis (quick)
- Command: `.venv python eval/eval.py --seedset quick`
- score **0.80718** folds [0.79773, 0.8159, 0.81124, 0.80783, 0.80318] n=6954 elapsed=10.9s score_std=0.0063 score_sem=0.00282
- vs untouched parent **0.80732** folds [0.79702, 0.81232, 0.81988, 0.80638, 0.80101] Δ **-0.00014**
- Fold deltas vs parent: +0.00071, +0.00358, **-0.00864**, +0.00145, +0.00217 (four up, fold 2 down). Inside fold noise.

## Same-fold worker ablations (not eval.py; same group split seed 20260910)
- parent-like (no zero-True, no shares): **0.80732** folds [0.79702, 0.81232, 0.81988, 0.80638, 0.80101] (matches eval parent)
- cryo-only: **0.80791** (+0.00059) folds [0.79418, 0.81447, 0.81844, 0.80638, 0.80608]
- shares-only: **0.80503** (−0.00229) folds [0.79063, 0.81877, 0.81124, 0.80711, 0.7974] std 0.00997
- both (shipped): **0.80718** matches eval.py

## LightGBM split counts on full data/train.csv
FoodShoppingShare 998 (rank 5), LuxuryShare 775 (rank 6) — used, not ignored. CryoSleep 146 (rank 17). log_TotalSpend 1346. Shares are collinear substitutes; they take splits without lifting accuracy.

Shipped code stays as hypothesized (do not silently drop shares). Final commit 5469a86.

## Finish
Wrote HANDOFF.md and proposals.json. Next bets: ablate GroupId; F-deck leftover planet from spend mix; discrete spend-pattern instead of collinear shares. Do not retry continuous LuxuryShare/FoodShoppingShare or blanket zero-spend CryoSleep=True.
