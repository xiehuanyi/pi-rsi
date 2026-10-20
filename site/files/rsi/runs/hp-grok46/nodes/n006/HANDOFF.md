# Handoff n006: Ridge as fourth log-space blend member
## Hypothesis
Keep the current equal-weight LGBM+XGB+CatBoost log-space blend. Add a fourth model: Ridge (alpha grid through 1000, as n002 needed) on one-hot categoricals plus log1p of skewed area fields, trained on log1p(SalePrice). Average four log preds then expm1+clip. Fit the linear pipeline on the labeled train frame only. Do not retune tree params.
## What I did
- Confirmed untouched parent quick RMSLE 0.12053 (same folds as n004).
- Added `src/linear_features.py` `LinearRidgeFeatures`: n002 layout (19 ordinal maps, 7 train-only one-hots with min-count-5 Other, median numerics, log1p of LotArea/GrLivArea/TotalBsmtSF/1stFlrSF/GarageArea, log1p TotalSF, TotalBath, variance mask). Stats fit on the labeled train frame only.
- Extended `BlendLogModel` in `src/model.py` with StandardScaler + RidgeCV (`logspace(0, 3, 31)` = alphas 1–1000). Tree params unchanged. Predict is the mean of four log preds, then expm1 and clip to `[0.5·ymin, 1.5·ymax]`.
- Rewired `train.py` to fit TabularFeatures for the trees and LinearRidgeFeatures for Ridge, then pass both matrices into the blend.
- Side diagnostic on the same `RandomState(20260910)` folds: per-member RMSLE and log-residual correlation. Did not change weights or tree params after seeing it.
## Result
- quick (untouched parent, this worktree): score 0.12053, folds=[0.11526, 0.12763, 0.10596, 0.11617, 0.13762], score_std=0.01097, score_sem=0.00491, n=1167, elapsed=61.4s. Command: `eval/eval.py --seedset quick`.
- quick (this node, 4-way blend): score 0.11896, folds=[0.10991, 0.12521, 0.10227, 0.1139, 0.14352], score_std=0.01434, score_sem=0.00641, n=1167, elapsed=65.3s. Same command. Delta vs parent quick: −0.00157.
- Folds 0–3 all improved (Δ −0.00535, −0.00242, −0.00369, −0.00227); fold 4 worsened +0.00590 (0.13762 → 0.14352). Mean drop is well below parent fold std (0.01097).
- Side diagnostic (same folds, not the evaluator): member means lgbm=0.12694, xgb=0.12636, cat=0.12062, ridge=0.12998, tree3=0.12053, all4=0.11896. Ridge folds 0–3 identical to n002; fold 4 ridge=0.16959. Log-residual corr(tree3, ridge) mean 0.82 (fold 4: 0.882). Ridge alphas [251.19, 251.19, 251.19, 316.23, 63.1].
- validation: not computed here (harness-only). Parent official validation was 0.1389.
- Final git commit: `89282ebeb1a67e8e24691a4b4ddd69f4f0a82437`.
## Mechanism
Ridge is a different encoding (one-hot location/type, log areas, additive quality) than the three GBDTs, so on ordinary Ames houses its log errors are only partly shared (corr ~0.78–0.85) and a 1/4 vote cuts RMSLE on every typical fold. CatBoost alone is already 0.12062, almost the whole 3-tree blend (0.12053); Ridge then supplies the extra typical-house signal. The same linear member is the n002 Edwards failure mode: on fold 4 it scores 0.16959 (alpha only 63) against tree3 0.13762, and residual corr rises to 0.882, so equal averaging pulls the blend to 0.14352. The mean −0.00157 is that tradeoff, not a new 0.01-class leap, and fold std went up (0.01097 → 0.01434). If the hidden holdout looks like folds 0–3, a small official gain is possible; if it holds the cheap Edwards palace (n002’s Id 524 suspicion), this node can lose to the 3-tree parent.
## Dead ends
- Equal 1/4 log-space average including an un-robustified Ridge: mean quick 0.11896 vs parent 0.12053 (Δ −0.00157 ≪ fold std). Not a failed wiring (tree3 diagnostic still 0.12053; ridge folds 0–3 match n002) — equal weight on the tail-hostile member is the limitation.
- Did not retune tree params or blend weights (hypothesis forbade both).
- Did not drop Edwards rows or cap areas; that would be a different hypothesis (n005 is already taking the tree-side version).
## Next hypotheses
- 1. Keep the 4-way blend but robustify only the Ridge member: winsorize/cap GrLivArea/TotalBsmtSF/TotalSF at a train quantile (e.g. 99th or 4000 sqft) on both train and predict, and/or exclude Edwards GrLivArea>4000 (or SalePrice<300000 and GrLivArea>4000) from the Ridge fit only. Folds 0–3 already show Ridge helps; fold 4 ridge 0.16959 is what undid the mean.
- 2. Replace equal 1/4 with OOF-only non-negative weights (sum to 1) on the four log-space members, fit inside the labeled train file, never on the predict file. CatBoost 0.12062 vs LGBM 0.12694 / XGB 0.12636; global NNLS should downweight the two weaker trees and possibly shrink Ridge if fold-4 OOF dominates.
- 3. Swap RidgeCV for HuberRegressor (same LinearRidgeFeatures, log1p target) so the linear vote stays complementary on typical houses without Edwards leverage. Alternative ablation: drop LGBM and XGB and blend only CatBoost + robust linear.
## Open questions
- Does the hidden 293-row holdout look like folds 0–3 (then 4-way should nibble parent 0.1389) or like fold 4 (then equal-weight Ridge can lose)?
- Is fold 4 still Id 1299 (Edwards, GrLivArea=5642, SalePrice=160000), and is Id 524 in the holdout?
- Would a global OOF weight on Ridge be ~0.25 (typical-house help) or near 0 (tail penalty)? It cannot be both.
- CatBoost alone almost matches the 3-tree blend; are LGBM and XGB dead weight under equal weights?
