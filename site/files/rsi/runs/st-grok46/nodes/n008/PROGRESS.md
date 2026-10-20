# n008 progress

## Start
- Node: CryoSleep remaining NA (spend=0 → True) + luxury/food spend shares.
- Parent n006 commit 214cf049774b6c60604d0bd2b46cae687ada7702, official 0.8166.
- Plan: measure untouched parent quick, then implement only this hypothesis in `src/features.py`.

## 2026-09-10 — untouched parent baseline
- Command: `eval/eval.py --seedset quick`
- **quick: score 0.80417** (folds [0.79063, 0.81375, 0.81484, 0.80638, 0.79522], score_std=0.00974, score_sem=0.00435, n=6954, elapsed=11.1s)
- Matches n006 shipped quick. This is the starting point.

## Data checks (data/train.csv)
- Cryo NA 186: spend==0 n=86 transported 0.7093; spend>0 n=100 transported 0.30. Matches hypothesis.
- Cryo True never spend (0 of 2422). Awake False with total==0: n=416, transported 0.596 (the known risk of filling NA zero-spend as True).
- Remaining Cryo NA after spenders-awake: 86.
- Luxury spend corr vs Transported −0.2753; luxury share corr −0.4462 (stronger than raw). Food/shopping share corr +0.020.

## Implementation
- `src/features.py`: `impute_cryosleep` (spend>0 → False, remaining NA & total==0 → True); `spend_share`; NUM_FEATURES += LuxuryShare, FoodShopShare.
- LightGBM hyperparameters unchanged.
- Sanity: 86 NA zero-spend → True, 100 NA spenders → False, 416 known False zero-spend kept, 0 Cryo NA left on train/test. Shares in [0,1], 0 when total=0.

## 2026-09-10 — hypothesized change, quick
- Command: `eval/eval.py --seedset quick`
- **quick: score 0.80748** (folds [0.79276, 0.8159, 0.81772, 0.80856, 0.80246], score_std=0.00915, score_sem=0.00409, n=6954, elapsed=11.4s)
- Untouched parent quick 0.80417. Delta **+0.00331**. Fold deltas vs parent: +0.00213, +0.00215, +0.00288, +0.00218, +0.00724. All five folds up; std 0.00974→0.00915.
- Inside expected +0.002 to +0.006; still below fold std (~0.009) so treat as a small consistent lift, not a jump.
- Commit `fc99718`. Next: ablate cryo-fill vs shares (not shipped) to see which part moved the score.

## Ablations (not shipped; same quick seed set)
- Cryo remaining-NA fill only: **quick 0.80562** (folds [0.78779, 0.81519, 0.82205, 0.80856, 0.7945], std=0.01274, sem=0.0057, n=6954, elapsed=11.0s). Delta vs parent **+0.00145**. Fold deltas: −0.00284, +0.00144, +0.00721, +0.00218, −0.00072 (mixed; std up).
- Spend shares only: **quick 0.80722** (folds [0.7885, 0.81304, 0.817, 0.81218, 0.80535], std=0.01008, sem=0.00451, n=6954, elapsed=11.3s). Delta vs parent **+0.00305**. Fold deltas: −0.00213, −0.00071, +0.00216, +0.00580, +0.01013 (two down).
- Both together is the only setting with all five folds up. Shares carry the mean lift; cryo fill adds a little and stabilizes folds.
- Full-train LightGBM split counts: FoodShopShare 862 (rank 6), LuxuryShare 724 (rank 8) — trees used them, not ignored. CryoSleep 144 (rank 19). GroupId 1945 (rank 2), LastNameSize 883 still high.
- Unique group-mate CryoSleep would fill only 57 of 186 NA (29 True / 28 False); 27 of those are spend=0. Blanket zero-spend True covers 86. 642 groups have mixed CryoSleep.
- Restored hypothesized `src/features.py` from git after ablations. Working tree clean at `fc99718`.

## Finish
- Writing HANDOFF.md and proposals.json. Shipped code is cryo remaining-NA True + LuxuryShare/FoodShopShare.
