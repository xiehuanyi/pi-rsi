# pi-rsi report: hp-grok46

- task: kaggle-house-prices; metric `score` (lower is better)
- worker: grok:grok-4.6 (xhigh); utility: grok:grok-4.5
- search: width_root=3 width=2 depth=4 max_nodes=10 parallel=2 patience=4
- stop reason: max_nodes; elapsed 1h02m
- baseline (root) official score: 0.1836
- best node: `n008` official score 0.1358
- held-out `kaggle` seed set: best 0.1166 vs baseline -
- reference scores: solid_public_lb 0.12
- cost: utility: 12 calls, $0.18, 4m32s; worker: 10 calls, $1.61, 1h41m

## Best path

- `root` 0.1836 — baseline: Baseline starter code. Official score: 0.1836.
- `n001` 0.1418 — LightGBM on full tabular features with ordinal/NA handling: Replaced 8-feature ridge with LightGBM on 84 tabular features (ordinal maps, train medians, UNK label cats, TotalSF/Age/RemodAge). Official validation RMSLE 0.1418 (n=293, std 0.1107, sem 0.014) vs parent 0.1836; |Δ|=0.0418 below the 0.05564 bar. Worker quick-set: 0.12694 vs ridge quick 0.16778.
- `n004` 0.1389 — LGBM+XGB+CatBoost log-space blend: Equal-weight LGBM+XGB+CatBoost log-space blend on unchanged TabularFeatures. Official validation RMSLE 0.13889 vs parent 0.1418 (Δ=−0.00291). Worker quick-set: 0.12053 vs parent quick 0.12694 (all five folds down; hard fold barely moved).
- `n006` 0.1369 — Add Ridge as fourth blend member: Added Ridge (alpha grid 1–1000 on one-hot cats + log1p areas) as a fourth equal-weight log-space blend member with unchanged LGBM+XGB+CatBoost. Official validation RMSLE 0.1369 vs parent 0.1389 (Δ −0.0020). Worker’s quick-set: 0.11896 vs parent 0.12053; folds 0–3 improved, fold 4 worsened.
- `n008` 0.1358 — Robustify Ridge areas / Edwards: Ridge-only change: train-99th caps on GrLivArea/TotalBsmtSF/1stFlrSF/TotalSF with BsmtFinSF1 clipped to the TotalBsmtSF cap, plus Ridge-fit drop of Edwards/cheap GrLivArea>4000; trees and equal 1/4 blend unchanged. Official validation RMSLE 0.13578 vs parent 0.1369 (Δ −0.00112). Worker quick-set 0.11638 vs parent quick 0.11896.

## All nodes

| id | parent | depth | status | verdict | score | Δparent | title | duration |
|---|---|---|---|---|---|---|---|---|
| root | - | 0 | done | baseline | 0.1836 | - | baseline | - |
| n001 | root | 1 | done | no_change | 0.1418 | 0.04179 | LightGBM on full tabular features with ordinal/NA handling | 6m42s |
| n002 | root | 1 | done | improved | 0.1422 | 0.04135 | Wide regularized linear model: ordinal + one-hot + log areas | 9m04s |
| n003 | root | 1 | done | improved | 0.1438 | 0.0398 | CatBoost native categoricals with minimal FE | 9m01s |
| n004 | n001 | 2 | done | no_change | 0.1389 | 0.00291 | LGBM+XGB+CatBoost log-space blend | 5m30s |
| n005 | n004 | 3 | done | no_change | 0.1452 | -0.00635 | Ames extras + Edwards outliers | 9m10s |
| n006 | n004 | 3 | done | no_change | 0.1369 | 0.00199 | Add Ridge as fourth blend member | 12m37s |
| n007 | n001 | 2 | done | no_change | 0.1477 | -0.00586 | Bath/porch/QualArea features and Edwards outliers | 7m00s |
| n008 | n006 | 4 | done | no_change | 0.1358 | 0.00112 | Robustify Ridge areas / Edwards | 17m35s |
| n009 | n006 | 4 | done | no_change | 0.1368 | 0.00014 | OOF-tuned 4-member weights | 14m06s |
| n010 | n002 | 2 | done | no_change | 0.1367 | 0.0055 | Cap Ames area outliers for linear model | 17m03s |

## Insights

# Insights (verified across nodes; each line cites the node)

- Full mixed-type tabular features plus log1p LightGBM beat a tiny numeric ridge on Ames because neighborhood/quality/area signals are sparse and nonlinear. [n001, score 0.1418]
- Monotone ordinal quality encodings (NA→0) let trees use quality gradients without treating Ex/Gd/TA as unordered labels. [n001, score 0.1418]
- TotalSF (basement+floors) dominated split gain over raw area proxies; Age/RemodAge also mattered. [n001, score 0.1418]
- Neighborhood one-hots plus ordinal quality/condition maps let a log-target linear model capture location and finish premia the 8-column ridge missed, cutting official RMSLE from 0.1836 to 0.14224. [n002, score 0.1422]
- Wide ~110-feature matrices need stronger Ridge regularization than alpha≤100; GCV sat on the cap until the grid was extended to 1–1000 (chosen ~200). [n002, score 0.1422]
- On this feature set ElasticNetCV ≈ Ridge (worker quick means 0.12966 vs 0.13125; l1_ratio stuck at 0.1), so L1 adds little once dummies are regularized. [n002, score 0.1422]
- Equal log-space averaging of three similar GBDTs can improve every quick fold yet shrink to a tiny holdout gain (official Δ=−0.00291), because the models’ residuals stay highly correlated. [n004, score 0.1389]
- The hardest quick fold barely moved (worker −0.00187), so complementary leaf/depth/cat biases alone do not fix Ames outlier houses. [n004, score 0.1389]
- Native CatBoost categoricals on Ames mixed fields plus TotalSF/Age and a log1p target cut official RMSLE from 0.1836 to 0.14379 versus size-only ridge because ordered target stats use neighborhood/quality the linear baseline never saw. [n003, score 0.1438]
- Worker quick-set moved the same way as validation (0.12187 vs ridge 0.16778), so the quick seed set tracked the official direction for this swap. [n003, score 0.1438]
- Training-only outlier drops can improve quick CV while hurting holdout if similar cheap palaces remain as prediction targets (quick −0.00235 vs official 0.14524 > parent 0.1389). [n005, score 0.1452]
- Aggregated bath/porch/quality×size features plus dropping zero-gain flags give only modest fold moves; they do not fix ~3× overprediction of cheap large homes when those rows stay in the eval set. [n005, score 0.1452]
- Partial log-residual correlation (~0.8) between a GBDT blend and Ridge means a 1/4 linear vote can help ordinary houses without delivering large mean RMSLE cuts. [n006, score 0.1369]
- Under equal weights, one fold where Ridge fails (high residual corr, weak alpha) can erase typical-fold gains and raise fold std. [n006, score 0.1369]
- CatBoost alone nearly matching the 3-tree blend implies weaker trees add little under equal averaging once a strong member dominates. [n006, score 0.1369]
- Train-only cheap-palace drops do not fix the same pattern at prediction time: Id 1299 stayed ~3× overpredicted when it was validation, so holdout twins can erase quick gains. [n007, score 0.1477]
- High train split gain for QualArea/TotalPorchSF did not translate to a clear official win versus parent 0.1418. [n007, score 0.1477]
- Inner OOF NNLS beating equal blend on train OOF does not imply outer gains: the 4-parameter simplex overfits correlated OOF columns and fails under train/predict shift. [n009, score 0.1368]
- A single global Ridge weight cannot handle both regimes: when the hard tail is held out, NNLS upweights Ridge on typical houses and hurts the held-out tail. [n009, score 0.1368]
- Living-area caps alone do not tame Ridge palace leverage when BsmtFinSF1 stays uncapped; Id 1299’s finished basement still drove ~1e6 preds until clipped to the TotalBsmtSF cap. [n008, score 0.1358]
- Dropping cheap/Edwards palaces from Ridge fit (not trees) improves other folds and luxury underprediction, but without predict-time caps fold-4 ridge stays ~0.17 when the palace is a target. [n008, score 0.1358]
- Equal-weight blend gains when Ridge stops casting a million-dollar vote even if trees still ~3–4× overpredict the cheap palace. [n008, score 0.1358]
- Cap finished-basement channels with TotalBsmtSF on palace rows: worker in-process showed uncapped BsmtFinSF1 as the largest log-price term on Id 1299. [n010, score 0.1367]
- Neighborhood/sale-condition-masked caps beat global ones: global p99 undercuts ordinary luxury; living-4000 alone left the palace fold high. [n010, score 0.1367]
- Do not drop train cheap-palaces when a held-out twin may appear: drop cannot fix folds that already hold the palace out and removes the only clipped training exemplar. [n010, score 0.1367]

## Dead ends

# Dead ends (do not retry; each line cites the node)

- HasGarage and HasBsmt added no LightGBM split gain on a full-public-train fit (redundant with GarageArea/TotalBsmtSF); kept but not valuable without an ablation. [n001]
- RidgeCV alphas 1–100: GCV always chose the upper bound 100 on the wide feature matrix; not usable without widening the grid. [n002]
- ElasticNetCV vs Ridge on the same quick folds: delta 0.0016 ≪ fold std 0.024, so switching models was not justified. [n002]
- Equal-weight LGBM+XGB+CatBoost log blend with no feature or weight changes: official 0.13889 vs parent 0.1418 (|Δ|=0.00291 < 0.04203) — not a meaningful holdout win despite worker quick −0.00641. [n004]
- Bundle of Ames extras + Edwards/cheap GrLivArea>4000 train drop: official score 0.14524 vs parent 0.1389 (no meaningful gain). [n005]
- QualGrLiv/extras do not rescue cheap-palace predictions (worker: Id 1299 still ~3.4× high on quick fold 4). [n005]
- Equal 1/4 log-space blend with un-robustified Ridge: official Δ −0.0020 vs parent 0.1389 is within |δ|<0.04451; worker’s quick Δ −0.00157 ≪ fold std. [n006]
- LGBM extras (TotalBath/TotalPorchSF/QualArea) plus Edwards train drop: official 0.14766 vs parent 0.1418 (no meaningful improvement; same directional failure mode as n005). [n007]
- Global OOF NNLS simplex weights on the un-robustified 4-member log blend: worker quick 0.12070 vs 0.11896 (Δ +0.00174, fold 4 +0.00830); official validation flat at 0.13676 vs 0.1369. [n009]
- Cap named areas at 4000 (or max(4000,p99)) without BsmtFinSF1 consistency: worker ridge-only fold 4 ~0.168, Id 1299 still ~1.08e6. [n008]
- Drop-only, no caps: ridge mean improves but fold 4 stays 0.16959 and Id 1299 stays ~1.12e6 (n005-style holdout risk). [n008]
- 99th on the four named columns without BsmtFinSF1 clip: fold-4 ridge 0.16405, Id 1299 still ~996k. [n008]
- Global living-4000 + LotArea/GarageArea p99 only: worker in-process mean 0.12905, fold 4 0.16874, Id 1299 still ~6.85×. [n010]
- Global p99 on listed area cols: worker in-process fold 4 ~0.163 with Id 1183 ratio ~0.35 (luxury flattened). [n010]
- Cheap-palace train drop: no fold-4 change when Id 1299 is already held out. [n010]
