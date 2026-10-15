# Proposal: proxy-aware evaluation for Kaggle

Status: design proposal, not an implemented configuration/API. Existing `quick`, `official_seedset`, and
`final_seedset` configuration remains unchanged. The scheduler currently selects on the official score.

## Principle

A local validation score is evidence about a chosen proxy distribution, not the hidden competition objective.
Public LB is another proxy (and an adaptively queried one), not an independent final test. Private LB is usually
unavailable until the competition ends. Never silently promote public-LB feedback into the search objective.

Separate two axes currently conflated by evaluation levels:

- **Data protocol:** sample IDs, split strategy, fold/repeat, groups/time boundaries, domain slices, metric.
- **Compute fidelity:** smoke/proxy/full training budgets, seeds, epochs, model sizes.

Increasing compute fidelity does not validate the assumed data distribution. Full-budget CV and a Kaggle
submission are different evaluations, not simply adjacent rungs of the same fidelity ladder.

## Four roles

| Role | Purpose | May drive automatic search? |
|---|---|---|
| development | cheap smoke runs and inner tuning | yes, provisional evidence only |
| selection | fixed local K-fold/repeated CV on development data | yes, authoritative local proxy |
| confirmation | untouched outer local holdout, or outer folds in a nested protocol | no, one locked candidate per registered protocol |
| external | public-LB submission; private-LB result when released | no by default; external observation only |

Selection CV is still adaptively overfit when many hypotheses are selected on it. A held-out confirmation split
must not be inspected by the planner or workers during search. If confirmation feedback triggers another search,
record the test as consumed; it is no longer an untouched final estimate. Nested CV is an expensive alternative:
the complete tuning/search procedure must stay inside each outer training fold, not merely a final model refit.
For very small datasets, make this trade-off explicit rather than claiming that ordinary CV is unbiased after search.

## Freeze a protocol before spending the search budget

A human approves the protocol with task-specific defaults:

- IID regression: shuffled K-fold; classification: stratification where valid.
- Repeated subjects/entities: group-aware folds. Do not scatter the same entity across train and validation.
- Temporal prediction: forward/rolling splits and any needed gap; no future-to-past leakage.
- Known domain shift: domain/location/time holdouts and predefined stress slices alongside the main proxy.

Persist a versioned split manifest with dataset fingerprint, row IDs, groups, fold/repeat IDs, seeds, metric and
aggregation. Freeze it for an experiment. Changing a split, dataset, metric, or pipeline contract creates a new
protocol; never compare its scores directly with old nodes as though they were measured on the same benchmark.

All learned preprocessing (imputation, feature selection, encodings, scaling) must fit within each fold's training
partition. Target encoding needs inner out-of-fold construction. Fix IDs and seeds across candidate comparisons.
Do not create a new random split per node: that confounds code changes with sampling changes.

## Evidence, selection, and promotion

Keep an evaluation ledger separate from node identity. Each record should include:

- node ID and exact code/artifact hash;
- protocol ID, data role, split/repeat/seed IDs, compute fidelity;
- fold/slice metrics, OOF predictions or per-item losses when appropriate;
- aggregate definition, uncertainty description, resource usage, status, timestamp;
- whether this evidence was exposed to search;
- external submission ID, model-training recipe, and reported leaderboard type when applicable.

Only compatible **selection** records can update `node.score`, the incumbent, `delta_best`, or patience.
Development results should not silently replace missing official scores. A full-budget rerun gets its own record.
Use paired comparisons on the same folds/items. Fold variation is a stability diagnostic, not automatically an
independent-samples standard error: training sets overlap, repeats are correlated, and many hypotheses were tried.
Do not let an auditor convert a small numerical gain into an unsupported claim of statistical significance.

For promoted candidates, assess predefined slice performance and stability as well as the mean proxy score.
If a robust aggregate or promotion gate is desired, predeclare its weights/thresholds; do not invent them after
seeing public LB. Different split schemes can be reported separately instead of forcing an arbitrary single score.

## Submission and shift monitoring

1. Select and lock the candidate using local selection evidence and the declared compute budget.
2. Evaluate the locked candidate once on confirmation, if configured. Report honestly, including regressions.
3. Refit using the declared full-training recipe and legal available labels; save the artifact and predictions.
   If confirmation labels enter this fit, subsequent confirmation scores are not fresh evidence.
4. Submit explicitly under a cap. Attach public LB to the exact artifact/node; do not replace the local incumbent.
5. Compare local and public *trends* across the small set of submitted candidates. Flag disagreement as possible
   split mismatch, leakage, noise, train-size differences, or shift—not proof of a particular cause.
6. Add private LB later as external evidence. Never imply it was accessible during search.

If a human wants to redesign the proxy after observing LB, create a new protocol/experiment and record that the
new protocol used external feedback. Public LB can inform diagnosis, but cannot then be called an untouched test.
Any preselected top-k confirmation benchmark must report all results; picking the best confirmation score turns
confirmation into selection. The same applies to choosing the maximum public-LB result after many submissions.

## Incremental integration with the current code

1. Add protocol/split manifests and CV evaluators to task packs. Keep existing CLI commands working.
2. Add role/protocol/fidelity metadata and a separate evaluation ledger; preserve `node.score` as the designated
   local selection proxy for compatibility.
3. Separate confirmation evaluation from external submission. Today `final_seedset = "kaggle"` in House Prices
   combines these concepts; migrate it to an explicit external-submission action rather than an implicit held-out test.
4. Make report sections explicit: local selection, confirmation, public LB, private LB. Avoid a generic “held-out”
   label for public LB. Record candidate identity alongside every number, including final top-k results.
5. Add protocol compatibility checks and promotion/feedback policies before enabling adaptive multi-fidelity search.

Acceptance checks: public-LB updates never change the incumbent; incompatible protocol scores cannot be ranked
as one benchmark; confirmation evidence is absent from worker/planner prompts; split manifests are reproducible;
fold preprocessing cannot train on held-out labels; submission evidence remains tied to its exact artifact.
