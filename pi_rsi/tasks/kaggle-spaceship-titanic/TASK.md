# Task: Kaggle Spaceship Titanic

Binary classification: predict whether each passenger was transported to another dimension, from home planet,
cabin, cryo-sleep status, age, VIP flag, amenity spending and name. Kaggle's "Getting Started" classification
competition.

## Goal
Maximize **accuracy** on unseen passengers.

## Deliverable
A reproducible pipeline: `python train.py --train <labeled.csv> --predict <features.csv> --out <pred.csv>` that trains
from scratch on the labeled file and writes `PassengerId,Transported` (True/False) for the prediction file. Under 15
minutes on CPU with the installed packages (pandas, numpy, scikit-learn, lightgbm, xgboost, catboost, scipy). No network.

## Metric and data
- `score` = accuracy, **higher is better**.
- `quick`: 5-fold CV on `data/train.csv` grouped by passenger group (gggg), for your iteration; costs 5 trainings.
- `validation`: a hidden holdout (about 20% of labeled rows, whole groups) kept outside the repository; the harness
  computes it after you finish. Do not try to locate or read it.
- `kaggle`: the final report trains on all labeled rows and submits predictions for the test rows to the public
  leaderboard.

## Known reference points
- This starter (logistic regression on spend + age + CryoSleep): about 0.77-0.78 accuracy.
- Solid solutions (group/cabin features, spend patterns, CryoSleep-consistent imputation, gradient boosting):
  0.80-0.82 on the public leaderboard; the top of the leaderboard is around 0.82-0.83.

## Constraints
- Keep the CLI contract and the output format. Do not modify `eval/` or `docs/`.
- Fit all preprocessing inside the training run. Group-aware validation matters: passengers in the same group share
  cabins and outcomes, so row-wise CV leaks.
- Deterministic seeds; CV gains below the fold standard deviation are noise, not progress.
