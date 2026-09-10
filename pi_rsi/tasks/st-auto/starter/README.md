# Spaceship Titanic workspace

- `train.py` — entry point; keep the CLI contract `--train --predict --out` and the output columns
  `PassengerId,Transported` (`True`/`False` strings matching `data/sample_submission.csv`).
- `src/` — features, models. Files under 400 lines; one concern per module.
- `data/train.csv` — public labeled split (~80% of Kaggle's train, whole passenger groups kept together);
  `data/test.csv` — Kaggle test features; `data/sample_submission.csv` — submission format. `docs/DATA.md`
  describes the columns.
- `eval/` — frozen evaluator. Do not edit.

```
python train.py --train data/train.csv --predict data/test.csv --out submission.csv
```

Iterate with `<python> eval/eval.py --seedset quick` (5-fold group-aware stratified CV on `data/train.csv`,
accuracy, higher is better). The official node score is computed by the harness on a hidden holdout you never
see. The final report submits the best node to Kaggle for the public leaderboard score.

Installed for you: pandas, numpy, scikit-learn, lightgbm, xgboost, catboost, scipy. The starter is a weak
logistic baseline; cabin/group features and gradient boosting are the usual next step.
