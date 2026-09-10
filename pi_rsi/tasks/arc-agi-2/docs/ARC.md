# ARC-AGI-2 in this task pack

Each task is a JSON object `{"train": [{"input": grid, "output": grid}, ...], "test": [{"input": grid}, ...]}`.
Grids are lists of rows of integers 0-9 (colors), 1x1 up to 30x30, and output shapes can differ from input shapes.
The rule that maps inputs to outputs must be inferred from the 2-5 train pairs and applied to each test input.
ARC-AGI-2 tasks require compositional reasoning (symbolic interpretation, contextual rules, multi-step
transformations); memorizing the 1000 training tasks does not transfer directly, which is why fine-tuned small
models score near zero without further ideas.

- `data/training/` — 1000 tasks with all outputs (use freely: fine-tuning data, augmentation source, held-out checks).
- `data/evaluation_inputs/` — the 120 public evaluation tasks with test outputs removed. The wrapper passes the level's
  subset of these to your solver; the hidden outputs are scored by the wrapper only.
- `eval/subsets.json` — which task ids belong to smoke (10), proxy (40, the official node score) and full (120).

Scoring: a task counts as solved (pass@2) only if every test input has an exactly correct grid among the two attempts.
`score = pass2 + 0.001 * cell_acc`, so exact matches dominate and cell accuracy only breaks ties. Beware that the
starter's fallback (returning the input grid) already yields cell_acc ≈ 0.8 because many outputs resemble inputs;
cell accuracy above that is a weak signal, exact matches are the real one.

Known levers from the ARC Prize literature (all allowed within the budget, all optional):
- Augmentation (rotations, flips, transpositions, color permutations) for training and for test-time voting.
- Test-time training: fine-tune on the eval task's own train pairs (leave-one-out) before predicting its test input;
  this is the single most effective known technique for fine-tuned LMs on ARC.
- Multiple sampled candidates with augmentation-consistency voting to pick the two attempts.
- Compact serializations that shorten sequences; per-task context trimming; smaller models decode faster.
- Program-synthesis / DSL search hybrids are allowed too, as long as they run offline inside the budget.
