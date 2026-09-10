# House Prices workspace

- `train.py` — entry point; keep the CLI contract `--train --predict --out` and the output columns `Id,SalePrice`.
- `src/` — features, models, anything else. Files under 400 lines; one concern per module.
- `data/train.csv` — 1,167 labeled rows (80% of Kaggle's train); `data/test.csv` — Kaggle test features;
  `data/sample_submission.csv` — submission format.
- `eval/` — frozen evaluator. Do not edit. `docs/data_description.txt` explains every column.

Iterate with `<python> eval/eval.py --seedset quick` (5-fold CV on data/train.csv, RMSLE, lower is better).
The official node score is computed by the harness on a hidden 20% holdout (293 rows) that you never see.
The final report submits the best node to Kaggle for the public leaderboard score.
