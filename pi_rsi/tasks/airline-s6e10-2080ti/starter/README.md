# GPU CatBoost starter

Edit `train.py` and `src/` only. Do not edit data, copied evaluator, manifests, task config or docs. Use only `data/` provided here; no raw/private data, external datasets or solutions.

```sh
/path/to/task/.venv/bin/python train.py --train data/quick_train.csv \
  --predict FEATURES.csv --out predictions.csv --seed 20261004 \
  --threads 8 --budget 60 --model-out model.cbm
```
`FEATURES.csv` has exactly the non-target columns (including id). The frozen evaluator creates it from quick-dev without labels; do not point --predict at labeled quick_dev.csv. Output exactly `id,satisfaction`, preserving IDs/order and finite [0,1] probabilities. Support --seed, --threads, --budget, --model-out along with required --train/--predict/--out. The evaluator owns scoring and enforces the whole-command cap. Save a model when available; adjacent model.metadata.json is optional diagnostic timing, not the score.

From the harness worktree (which includes frozen `eval/`):
```sh
/path/to/task/.venv/bin/python eval/eval.py --agent-dir . --seedset quick \
  --out runs/quick/metrics.json --python /path/to/task/.venv/bin/python
```
From the task-pack root, use `--agent-dir starter` with `eval/eval.py`. Harness GPU queue runs official validation; no worker command exposes it.

Baseline: 400 depth-6 GPU CatBoost trees, learning rate .08, raw numeric/rating columns, native one-hot categories. `src/features.py` is the natural location for controlled feature hypotheses. ID is always dropped. No early stopping, target encoding, or label-dependent feature selection. All future learned preprocessing must fit within supplied training only. Quick-dev may diagnose but may not train a quick model; official/final labels are never available. Same-user workers are trusted to respect the documented boundary, not protected by a sandbox.

Only authorized RTX 2080 Ti physical index 1, UUID GPU-2c54fc50-8962-5ef4-a42f-45752aedef9d; CatBoost uses logical GPU 0. Guard verifies identity before fitting, without altering the caller's mask. CPU ≤8 threads. GPU fit is not bitwise deterministic despite fixed seed. See TASK.md and docs/PROTOCOL.md for research limits, measured baselines and the sealed-final policy.
