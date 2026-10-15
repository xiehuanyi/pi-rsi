# Airline satisfaction — S6E10 / RTX 2080 Ti

Optimize **ROC-AUC**, higher is better, of `P(satisfaction=1)` using only supplied competition CSVs. Deliver an improved, runnable `train.py` and supporting `src/` code, with a hypothesis, ablation evidence, timing, and limitations. No uploads, leaderboard probing, Kaggle submissions, external data, or copied solutions.

## Research brief
Under the same compute budget, test whether service-rating interactions and passenger-segment features improve over GPU CatBoost. Examples: rating dispersion/contrasts, consistent high/low service ratings, and interactions with travel type, loyalty, class or age. Use controlled ablations rather than blind hyperparameter search. One hypothesis per node, **at most three development trials**; repeated seeds where appropriate, with seed choices recorded, never selecting seeds by official labels.

The caller's first campaign is 8 sequential research nodes, at most 16 implementation attempts; total campaign expansions across continuations must never exceed 128 (root excluded). Stop for justified saturation rather than exhausting a budget artificially. These search limits must be supplied by the caller's experiment configuration; this task pack does not launch an experiment.

## Candidate contract
```sh
python train.py --train LABELED.csv --predict FEATURES.csv --out PREDICTIONS.csv \
  --seed 20261004 --threads 8 --budget 60 --model-out MODEL.cbm
```
Accept all arguments. Write exactly `id,satisfaction`, in input prediction order, with one finite probability in [0,1] per ID. ID must never be a predictive feature. The CLI must fit from scratch on only the supplied labeled training rows; `--predict` has no target. Model output is optional for non-CatBoost methods, but write it when available. `--budget` is seconds; the evaluator enforces a hard whole-CLI cap (startup, preprocessing, fitting, prediction and saving), stricter than a fit-only cap.

Workers edit only starter code, not data, evaluator, manifests, splits or task configuration. Read only worker-visible training/test data. Do not read raw sources, `private/`, held-out labels, or private evaluation artifacts, even if same-user filesystem access permits it. Do not hardcode predictions or exploit IDs. This is a cooperative evaluator boundary, **not an OS sandbox**.

## Frozen levels
- **quick:** fixed 50,000 train / 10,000 dev rows, disjoint subsets of the training pool. 60-second cap. Both sets are worker-visible; do not fit on quick-dev labels during a quick run.
- **validation:** fit on all 489,744 training-pool rows; predict 104,945 separate search-validation rows. 180-second cap. Only the evaluator reads official labels. These adaptive search scores are not independent confirmation.
- **final:** same frozen training pool and method, 104,946 untouched held-out rows; 240-second cap. Implemented but sealed with `final_seedset=''` and `final_eval_root=false`. Enable explicitly only at the end of the entire campaign, not after the initial 8-node pilot. Never a Kaggle submission.

Stratified 70/15/15 split seed: **20261004**. Fit all learned transformations/encoders within training rows only. If using early stopping, its labels must come from an internal split of the supplied training rows, never quick prediction labels or official/final labels. Validation and final must use the same method; no level-specific tuning or changed training pool.

## Hardware and commands
Only RTX 2080 Ti physical index 1 / `GPU-2c54fc50-8962-5ef4-a42f-45752aedef9d`, 11 GB VRAM; inside the provided mask use logical GPU **0**. No RTX 3090, visibility expansion, global environment changes or package downloads. CPU preprocessing ≤8 threads. Both frozen evaluator and starter verify physical and logical identity before fitting. GPU queue mode is mandatory for harness evaluations; do not use its CPU-only monitored-eval path.

From a worker worktree with copied frozen `eval/`:
```sh
/path/to/task/.venv/bin/python eval/eval.py --agent-dir . --seedset quick \
  --out runs/quick/metrics.json --python /path/to/task/.venv/bin/python
```
The harness alone schedules official validation using the original frozen evaluator. No worker validation command is exposed.

## Measured starter reference (2026-10-04; one seed, no search)
400 trees, depth 6, learning rate 0.08, native categorical features, GPU Plain boosting, no early stopping or feature engineering.

| Level | ROC-AUC | GPU fit seconds* | Whole candidate seconds | Evaluator seconds |
|---|---:|---:|---:|---:|
| quick | 0.9525373326142100 | 2.145 | 3.588 | 3.834 |
| validation | 0.9571858140052044 | 2.573 | 4.845 | 5.453 |

*Fit timer is reported by starter; whole candidate and evaluator-routine timers are independently measured (evaluator timer excludes its own interpreter/import startup). GPU identity was independently verified. Raw measured metrics are under `_newtask/baseline/`; public summary: `docs/BASELINE.json`. A separate wrapper integration repeat scored quick 0.9525372110676713, demonstrating fixed-seed GPU variation; it was not parameter tuning. GPU CatBoost is not bitwise deterministic. These checks are not a reliable uncertainty estimate; uncertainty is unknown, not zero. ROC-AUC is pairwise: no fabricated per-row contributions, paired-noise statistics or unjustified standard errors are provided.

See `docs/PROTOCOL.md`, `docs/HARDWARE.md`, and `docs/DATA.md` for details.
