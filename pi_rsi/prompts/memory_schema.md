# Research memory schema

This wiki follows the LLM Wiki pattern, specialized for experimental research.

- raw/ contains immutable evidence packets. Experiment measurements and worker interpretations
  are recorded separately. New measurements produce new packets; corrections never erase history.
- revisions/<revision>/wiki/ contains generated knowledge pages: observations, hypotheses, experience.
  Every page has scope, evidence for and against, alternatives, status, and a discriminating next test.
- AGENDA.md is a revisable synthesis: motivation, method rationale, what changed, unanswered questions,
  and experiments that can distinguish competing explanations.
- CURRENT.json is the atomic published revision pointer. Generated pages are views of state.json.
- Node MEMORY.md and memory.json preserve the exact context used by each worker.

Treat supported as supported within stated conditions, not established universal fact.
Numerical agreement with an evaluator does not verify a causal explanation.
Preserve failed attempts with their conditions. An implementation failure is not scientific refutation.
Evidence supporting and opposing the same scoped proposition requires mixed status until resolved.
Keep source IDs. Repeating a summary does not create new evidence.
Novelty and significance require relevant literature; identify missing literature explicitly.
Only local selection evidence is automatically captured. Final/confirmation results and public leaderboard
feedback are not automatic memory inputs. Do not import them into an ongoing search as untouched evidence.

The task objective and protocol remain the experiment's contract. Human edits to this schema can
guide emphasis, but do not relax evidence-reference validation or change historical records.
