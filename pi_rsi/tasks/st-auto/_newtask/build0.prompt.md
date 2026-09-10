You are the task-pack builder (data + evaluation engineer) of pi-rsi, an automated research loop. Build a complete,
runnable task pack in the current directory (`/media/xieh0a/data/huanyi/Research/AutoResearch/pi-rsi/pi_rsi/tasks/st-auto`) for the problem below, following the decisions the human
confirmed. Research workers will later edit only the starter code; the evaluator you write is frozen and is the
single source of truth for scores, so it must be correct, deterministic and leakage-safe.

# Problem
Kaggle Spaceship Titanic: predict whether each passenger was Transported (binary), competition metric is accuracy; we can submit to Kaggle (competition slug spaceship-titanic)

# Confirmed decisions
{
 "deliverable": "kaggle_pipeline: End-to-end Kaggle training + submission pipeline — A CLI/script that trains on train.csv, writes OOF/CV metrics, predicts on test.csv, and produces a submission.csv with columns PassengerId,Transported (boolean or string matching the competition format). Includes preprocessing, feature engineering from Cabin/PassengerId/Name, and a tunable model.",
 "metric": "accuracy: Accuracy (higher is better) — Official Spaceship Titanic competition metric; submissions are scored by fraction of correct Transported labels.",
 "cv_grouping": "GroupKFold / group-aware stratified folds by PassengerId group (recommended)",
 "model_family": "Gradient boosting (LightGBM/XGBoost/CatBoost) with light FE (recommended)",
 "submission_dtype": "Boolean True/False strings matching sample_submission (recommended)",
 "compute_budget": "Light: few models, default-ish params, minutes (recommended)",
 "protocol": {
  "quick": "Stratified k-fold (e.g. 5-fold) CV on train.csv only, reporting mean±std accuracy. Optionally group folds by PassengerId group prefix to reduce within-group leakage. Agent may see full train labels and CV scores; keep no held-out slice at this stage.",
  "validation": "Hold out a fixed stratified (or group-aware) validation split from train.csv that the agent never tunes against iteratively as a pseudo-leaderboard; evaluate accuracy once after model selection on CV. Hide this holdout's labels from repeated agent feedback to limit overfitting to a small local set.",
  "final": "Train on all train.csv (or CV-chosen config), predict test.csv, write submission.csv, and score via Kaggle API for competition slug spaceship-titanic. Keep Kaggle public/private leaderboard labels fully hidden from the agent; only return the public score (and optionally private if available) as the final metric. Do not join test labels from any source."
 }
}

# Data profile
- sample_submission.csv (58 KB)
  rows=4277 cols=2
  columns: PassengerId, Transported
  sample: 0013_01, False
  sample: 0018_01, False
  sample: 0019_01, False
- test.csv (364 KB)
  rows=4277 cols=13
  columns: PassengerId, HomePlanet, CryoSleep, Cabin, Destination, Age, VIP, RoomService, FoodCourt, ShoppingMall, Spa, VRDeck, Name
  sample: 0013_01, Earth, True, G/3/S, TRAPPIST-1e, 27.0, False, 0.0, 0.0, 0.0, 0.0, 0.0, Nelly Carsoning
  sample: 0018_01, Earth, False, F/4/S, TRAPPIST-1e, 19.0, False, 0.0, 9.0, 0.0, 2823.0, 0.0, Lerome Peckers
  sample: 0019_01, Europa, True, C/0/S, 55 Cancri e, 31.0, False, 0.0, 0.0, 0.0, 0.0, 0.0, Sabih Unhearfus
- train.csv (787 KB)
  rows=8693 cols=14
  columns: PassengerId, HomePlanet, CryoSleep, Cabin, Destination, Age, VIP, RoomService, FoodCourt, ShoppingMall, Spa, VRDeck, Name, Transported
  sample: 0001_01, Europa, False, B/0/P, TRAPPIST-1e, 39.0, False, 0.0, 0.0, 0.0, 0.0, 0.0, Maham Ofracculy, False
  sample: 0002_01, Earth, False, F/0/S, TRAPPIST-1e, 24.0, False, 109.0, 9.0, 25.0, 549.0, 44.0, Juanna Vines, True
  sample: 0003_01, Europa, False, A/0/S, TRAPPIST-1e, 58.0, True, 43.0, 3576.0, 0.0, 6715.0, 49.0, Altark Susent, False
Raw data is under `/media/xieh0a/data/huanyi/Research/AutoResearch/pi-rsi/pi_rsi/tasks/st-auto/data/raw/` (already downloaded). Do not download anything else.

# Task pack contract (must match exactly)
```
/media/xieh0a/data/huanyi/Research/AutoResearch/pi-rsi/pi_rsi/tasks/st-auto/
  task.toml        harness config (schema below)
  TASK.md          brief for the workers: goal, deliverable, metric, protocol, reference points, constraints
  setup.sh         creates .venv (use `uv venv --python 3.12 .venv` and `uv pip install --python .venv/bin/python -r requirements.txt`),
                   then runs prepare.py with .venv/bin/python
  requirements.txt pinned packages
  prepare.py       builds the split: starter/data/ (what workers see), private/ (hidden labels, NEVER under eval/ or starter/)
  eval/eval.py     frozen evaluator (CLI: --agent-dir --seedset {quick|validation|final...} --out --python --quiet)
  starter/         the code workers edit: entry point + src/ modules + README.md; must run end to end on the starter
  docs/            column descriptions / rules the workers may read
```
task.toml schema (all keys shown; adjust values):
```toml
name = "st-auto"
[task]
brief = "TASK.md"
docs = ["docs/DATA.md"]
starter_dir = "starter"
eval_dir = "eval"
python = ".venv/bin/python"
[eval]
eval_command = "{python} {task_dir}/eval/eval.py --agent-dir {worktree} --seedset {seedset} --out {out} --python {python} --quiet"
worker_eval_command = "{python} eval/eval.py --seedset {seedset} --python {python}"
worker_val_command = ""          # "" means the validation level is hidden from workers
seedsets = ["quick", "validation", "final"]
official_seedset = "validation"
final_seedset = "final"
final_eval_root = false
quick_seedset = "quick"
eval_timeout_s = 2400
higher_is_better = true|false
score_key = "score"
reference_scores = { starter = 0.0 }   # fill with the measured starter score and any known reference
```
Evaluator rules:
1. `--seedset quick` must be runnable by workers from inside their worktree with only `starter/` contents + `eval/`
   (typically K-fold CV on the public labeled part, grouped/time-ordered when the data needs it).
2. `--seedset validation` uses hidden labels from `/media/xieh0a/data/huanyi/Research/AutoResearch/pi-rsi/pi_rsi/tasks/st-auto/private/` (path resolved relative to eval.py's parent's
   parent, i.e. `Path(__file__).resolve().parent.parent / "private"`), trains the agent's pipeline on the public part
   and scores the hidden part. Write `per_item` = [{"id", "value"}] (per-row contributions whose mean is the score, or
   set "score_transform" = "sqrt_mean" for RMSE-like metrics) so the harness can do paired noise estimates. Also write
   "score_std", "score_sem", "n".
3. `--seedset final` is the last, most expensive check (a Kaggle submission via the `kaggle` CLI when the problem is a
   competition the human can submit to, otherwise a larger hidden set). If submitting, poll `kaggle competitions
   submissions -c <comp> --csv`; the status string contains "complete" (case-insensitive substring match).
4. The output JSON always has "score" (float) at the top level; on failure write "score": null and "error".
5. The agent contract is a CLI: `python train.py --train <labeled.csv> --predict <features.csv> --out <pred.csv>` (or an
   equivalent that fits the deliverable) — document it in TASK.md and starter/README.md.
6. The starter must be simple but valid (a baseline a strong solution beats by a wide margin).

Steps:
1. Write all files. 2. `bash setup.sh`. 3. Run the evaluator on the starter for quick and validation:
   `.venv/bin/python eval/eval.py --agent-dir starter --seedset quick --python $PWD/.venv/bin/python` and the same
   with validation; fix until both work. 4. Put the measured starter scores into TASK.md and task.toml reference_scores.
5. Write `NEWTASK.md`: decisions, split design, leakage considerations, how to run.
Finish with one line: `NEWTASK_RESULT: {"ok": true|false, "starter_quick": <float>, "starter_validation": <float>, "notes": "..."}`
