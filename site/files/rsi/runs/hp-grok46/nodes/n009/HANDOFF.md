# Handoff n009: OOF-tuned 4-member NNLS weights
## Hypothesis
Keep TabularFeatures, LinearRidgeFeatures, and the four models (LGBM/XGB/CatBoost/Ridge) with current params. Inside each training run, compute out-of-fold log-space preds on the labeled train file (5-fold) and fit non-negative weights that sum to 1 by least squares on log1p(y). Use those weights on the predict file. Never peek at predict-file labels or the hidden holdout.
## What I did
- Confirmed untouched parent (n006 equal 1/4 blend) quick RMSLE on this worktree.
- Replaced equal averaging in `src/model.py` `BlendLogModel` with inner `KFold(5, shuffle=True, random_state=42)` OOF log preds for the four members, `scipy.optimize.nnls` vs log1p(y), L1-renormalize to the simplex, then a full-data refit. Predict is the weighted log sum, then expm1 + the same `[0.5·ymin, 1.5·ymax]` clip. Tree and Ridge params unchanged.
- Features still fit once on the labeled train frame (no target encoding); OOF is for the four regressors only. `train.py` wiring unchanged aside from the docstring.
- Logged per-run `OOF_WEIGHTS` / `OOF_RMSLE` to stdout (captured in `metrics.quick.log`).
## Result
- quick (untouched parent, this worktree): score 0.11896, folds=[0.10991, 0.12521, 0.10227, 0.1139, 0.14352], n=1167, elapsed=60.7s. Command: `eval/eval.py --seedset quick`.
- quick (this node, OOF NNLS weights): score 0.12070, folds=[0.11114, 0.12452, 0.10168, 0.11434, 0.15182], score_std=0.01718, score_sem=0.00769, n=1167, elapsed=307.3s. Same command. Delta vs parent quick: +0.00174 (worse). Fold deltas vs parent: +0.00123, −0.00069, −0.00059, +0.00044, +0.00830.
- Inner OOF diagnostics (train.py stdout, not the evaluator) for the five outer train files: ridge weights [0.1409, 0.0285, 0.2157, 0.0865, 0.4765]; CatBoost usually largest except outer fold 4. Inner NNLS RMSLE beat inner equal on every train file, as a 4-column LS fit on those same OOF rows must.
- validation: not computed here (harness-only). Parent official validation was 0.1369.
- Final git commit: `27f73180761ff07cd0605719aa4ab528bd475fda`.
## Mechanism
OOF NNLS does not learn a compromise weight. It copies whichever regime is in the labeled train file. On outer folds 0–3 the cheap-palace tail is inside train, Ridge’s inner OOF RMSLE is 0.13–0.15, and its weight shrinks (0.03–0.22). On outer fold 4 that tail is the predict set, so inner OOF is only typical houses: Ridge is the best member there (inner RMSLE 0.11223 vs CatBoost 0.11263) and gets weight 0.4765. Applying that Ridge-heavy mix to the held-out tail raises fold 4 from parent 0.14352 to 0.15182. Equal 1/4 was accidentally more robust to that train/predict shift. LGBM/XGB weights also jump (0.02–0.38) on ~933 rows of highly correlated OOF columns, so the 4-parameter simplex overfits inner CV and does not transfer. Runtime stayed fine (~61s per train.py, 307s for five folds).
## Dead ends
- Global OOF NNLS weights on the un-robustified 4-member log blend: quick 0.12070 vs parent 0.11896 (Δ +0.00174), fold 4 +0.00830. Inner NNLS beating inner equal did not predict outer improvement. Do not retry learned simplex weights until the linear member is tail-safe (or the vote is gated on size at predict time).
- Did not retune tree params, cap areas, drop Edwards rows, or shrink weights toward equal (hypothesis forbade bundling).
## Next hypotheses
- 1. Robustify only the Ridge member: winsorize/cap GrLivArea/TotalBsmtSF/TotalSF at a train-only quantile (99th or 4000 sqft) on train and predict linear features, and/or exclude Edwards GrLivArea>4000 from the Ridge fit only. Equal 1/4 (or a small fixed Ridge vote) should then keep folds 0–3 without the fold-4 linear blow-up. This node showed learned weights cannot substitute for that.
- 2. Size-gated linear vote: fit a train-only area threshold (e.g. GrLivArea 4000 or 99th percentile). Below it, use the 4-way (or CatBoost+Ridge) log blend; above it, drop Ridge and use trees/CatBoost only. That is an input-dependent weight, which a single global w_ridge cannot be.
- 3. Replace RidgeCV with HuberRegressor on the same LinearRidgeFeatures / log1p target, optionally drop LGBM and XGB (their OOF weights were unstable) and average only CatBoost + robust linear.
## Open questions
- If Ridge is winsorized, does a later OOF NNLS then settle on a stable ~0.15–0.25 Ridge weight, or do LGBM/XGB still thrash?
- Is the hidden 293-row holdout like folds 0–3 (equal-4 n006 should nibble) or like fold 4 (this node’s 0.48 Ridge weight would lose more than n006)?
- Would a shrunk meta-learner (mix NNLS with equal 1/4) have saved fold 4, or still leave Ridge too heavy whenever the tail is absent from train?
