# Task: Kaggle Spaceship Titanic

Binary classification: predict whether each passenger was transported to another dimension after the Spaceship Titanic
hit a spacetime anomaly. This is Kaggle's "Getting Started" classification competition (`spaceship-titanic`).

## Goal
Maximize **accuracy** on unseen passengers (official competition metric).

## Deliverable
A reproducible CLI:

```
python train.py --train <labeled.csv> --predict <features.csv> --out <pred.csv>
```

Train from scratch on the labeled file and write `PassengerId,Transported` for every row in the prediction file.
`Transported` must be `True`/`False` (boolean or the strings `"True"`/`"False"`), matching `data/sample_submission.csv`.
Fit all preprocessing inside the training run. Under 15 minutes on CPU with the installed packages (pandas, numpy,
scikit-learn, lightgbm, xgboost, catboost, scipy). No network.

## Metric and data
- `score` = accuracy, **higher is better**.
- `quick`: 5-fold group-aware stratified CV on `data/train.csv` (folds keep `PassengerId` group prefix `gggg` together
  and roughly preserve the label rate). Use this while iterating; it costs 5 trainings. You may see these scores.
- `validation`: a hidden holdout (~20% of Kaggle's labeled rows, whole groups) kept outside the repository. The harness
  trains on `data/train.csv` and scores this holdout once after you finish. Do not try to locate, read, or tune against it.
- `final`: the harness concatenates the public train with the hidden holdout, predicts `data/test.csv`, writes
  `submission.csv`, and submits to Kaggle. You never see test labels or the private leaderboard.

`data/train.csv` is the public labeled split (not the full Kaggle train). `data/test.csv` is the official Kaggle test
features (no labels). `docs/DATA.md` describes the columns.

## Known reference points
- This starter (logistic regression on log-spend, age, CryoSleep): **0.76359** mean 5-fold group CV (`quick`);
  **0.76481** on the hidden holdout (`validation`). Fold scores were `[0.77283, 0.74479, 0.76995, 0.76923, 0.76115]`.
- Solid solutions (cabin deck/num/side, passenger-group size, CryoSleep-consistent spend imputation, gradient boosting):
  about 0.80–0.82 on the public leaderboard. The top of the public leaderboard is around 0.82–0.83.
- A 0.01 CV gain that is smaller than the fold standard deviation is usually noise.

## Constraints
- Keep the CLI contract and the output columns. Do not modify `eval/` or `docs/`.
- Group-aware validation matters: people in the same `PassengerId` group often share a cabin and have correlated
  outcomes, so row-wise K-fold leaks. Do not use test-set labels from any source.
- Deterministic seeds. No network. Do not submit to Kaggle yourself; the harness owns the `final` seed set.
