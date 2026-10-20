# n009 progress

## Plan
Hypothesis: keep TabularFeatures, LinearRidgeFeatures, and LGBM/XGB/CatBoost/Ridge params from n006; replace equal 1/4 log-space weights with non-negative weights that sum to 1, fit by least squares on inner 5-fold OOF log1p preds vs log1p(y) from the labeled train file only.

## 2026-09-10 start
- Worktree at parent commit `89282ebeb1a67e8e24691a4b4ddd69f4f0a82437` (n006 4-way equal blend).
- Next: measure untouched parent quick RMSLE before any code change.

## Before parent quick eval
- Command: `eval/eval.py --seedset quick` with task venv python.
- Expectation from n006 handoff: score 0.11896, folds=[0.10991, 0.12521, 0.10227, 0.1139, 0.14352], elapsed ~65s.

## After parent quick eval (untouched n006 code)
- quick: score 0.11896, folds=[0.10991, 0.12521, 0.10227, 0.1139, 0.14352], n=1167, elapsed=60.7s.
- Matches n006 handoff exactly. This is the baseline to beat.
- Next: implement inner 5-fold OOF + scipy nnls (non-negative, renormalized to sum 1) on log-space member preds. Features stay fit on the full labeled train frame (no target encoding). Models retrained on all labeled rows; weights applied at predict time.

## Implementation
- `src/model.py`: inner `KFold(5, shuffle=True, random_state=42)` OOF for LGBM/XGB/CatBoost/Ridge; `scipy.optimize.nnls` on OOF log preds vs log1p(y); renormalize to sum 1; full-data refit; weighted log sum then expm1+clip. Tree/Ridge params unchanged.
- `train.py`: docstring only.
- Commit: `27f7318` Replace equal 1/4 blend with OOF NNLS log-space weights.
- Features still fit once on the labeled train frame (no target encoding, so OOF is for the four regressors only).

## Before NNLS quick eval
- Command: `eval/eval.py --seedset quick` with task venv python.
- Expect ~6x parent runtime (~6–7 min) because each train.py does 5 inner fits + 1 full fit.

## After NNLS quick eval
- Command: `eval/eval.py --seedset quick` with task venv python.
- quick: score 0.12070, folds=[0.11114, 0.12452, 0.10168, 0.11434, 0.15182], score_std=0.01718, score_sem=0.00769, n=1167, elapsed=307.3s.
- vs untouched parent quick 0.11896, folds=[0.10991, 0.12521, 0.10227, 0.1139, 0.14352]: mean Δ=+0.00174 (worse). Fold deltas: +0.00123, −0.00069, −0.00059, +0.00044, +0.00830.
- Inner OOF diagnostics (train.py stdout in metrics.quick.log, not the evaluator):
  - fold0 weights lgbm=0.0213 xgb=0.3762 cat=0.4616 ridge=0.1409; inner RMSLE nnls=0.12144 equal=0.12251
  - fold1 weights lgbm=0.2577 xgb=0.0476 cat=0.6661 ridge=0.0285; inner RMSLE nnls=0.12261 equal=0.12491
  - fold2 weights lgbm=0.0758 xgb=0.2859 cat=0.4226 ridge=0.2157; inner RMSLE nnls=0.11988 equal=0.12037
  - fold3 weights lgbm=0.2260 xgb=0.1499 cat=0.5375 ridge=0.0865; inner RMSLE nnls=0.11874 equal=0.11997
  - fold4 weights lgbm=0.0827 xgb=0.1341 cat=0.3067 ridge=0.4765; inner RMSLE nnls=0.10611 equal=0.10797 (ridge 0.11223, cat 0.11263)
- Mechanism: when the hard outer fold is held out, inner OOF on remaining typical houses rates Ridge as the best member (0.11223) and NNLS gives it 0.48 weight; that Ridge-heavy blend then fails on the tail (eval 0.15182 vs equal-4 0.14352). When the tail is inside train, Ridge inner OOF is 0.13–0.15 and its weight shrinks. A single global weight cannot do both jobs. Inner NNLS always beat inner equal on the train OOF (overfit of 4 correlated columns on ~933 rows) but did not transfer.
- Hypothesis refuted on the quick set. Do not bundle a follow-up change in this node.
- Final commit: `27f73180761ff07cd0605719aa4ab528bd475fda`
