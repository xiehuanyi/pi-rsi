# Task: Kaggle House Prices (Advanced Regression Techniques)

Predict the sale price of houses in Ames, Iowa from 79 explanatory variables (lot size, quality ratings, year built,
neighborhood, basement/garage details, ...). This is Kaggle's "Getting Started" regression competition.

## Goal
Minimize **RMSLE** (root mean squared error between log1p(prediction) and log1p(SalePrice)) on unseen houses.

## Deliverable
A reproducible pipeline: `python train.py --train <labeled.csv> --predict <features.csv> --out <pred.csv>` that trains from
scratch on the given labeled file and writes `Id,SalePrice` for the prediction file. It must run in under 15 minutes on
CPU with the packages already installed (pandas, numpy, scikit-learn, lightgbm, xgboost, catboost, scipy). No network.

## Metric and data
- `score` = RMSLE, **lower is better**.
- `quick`: 5-fold CV on `data/train.csv` (1,167 labeled rows), for your iteration; it costs 5 trainings.
- `validation`: a hidden holdout of 293 labeled rows kept outside the repository; the harness computes it after you
  finish. Do not try to locate or read it.
- `kaggle`: the final report trains on all 1,460 labeled rows and submits predictions for the 1,459 test rows to the
  public leaderboard.

## Known reference points
- This starter (ridge on 8 numeric features): about 0.20 RMSLE.
- Typical solid solutions (feature engineering + gradient boosting / regularized linear blends): 0.11–0.13 on the
  public leaderboard. Scores far below 0.10 on the leaderboard come from leaked labels and are not a target.

## Constraints
- Keep the CLI contract and the output format. Do not modify `eval/` or `docs/`.
- Fit all preprocessing inside the training run (no statistics from the prediction file's targets; it has none).
- Deterministic seeds; CV improvements below the fold standard deviation are noise, not progress.
