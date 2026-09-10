# Spaceship Titanic workspace

- `train.py` — entry point; keep the CLI contract `--train --predict --out` and the output columns
  `PassengerId,Transported` (True/False).
- `src/` — features, models. Files under 400 lines; one concern per module.
- `data/train.csv` — 80% of Kaggle's labeled rows (whole passenger groups); `data/test.csv` — Kaggle test features;
  `data/sample_submission.csv` — submission format. `docs/` describes the columns.
- `eval/` — frozen evaluator. Do not edit.

Iterate with `<python> eval/eval.py --seedset quick` (5-fold group CV on data/train.csv, accuracy, higher is better).
The official node score is computed by the harness on a hidden 20% holdout you never see. The final report submits
the best node to Kaggle for the public leaderboard score.
