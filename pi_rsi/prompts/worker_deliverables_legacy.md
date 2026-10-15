9. Finish by writing `$node_dir/HANDOFF.md` (schema below) and `$node_dir/proposals.json` (schema below). Both are mandatory; the harness parses them. If you are out of budget, a short handoff beats none.

# HANDOFF.md schema (markdown, keep these exact section headers)
```
# Handoff $node_id: <title>
## Hypothesis
<one paragraph>
## What I did
<bullets; name the files/functions changed>
## Result
<numbers with seed set and command, e.g. "quick: score 5210 (was 3495); validation: score 5044". Include the git commit hash of the final state.>
## Mechanism
<why it worked or did not, in terms of the task, not in terms of code>
## Dead ends
<bullets: things tried in this node that did not help, with the numbers>
## Next hypotheses
<ranked bullets, 1-3 items, mirrored in proposals.json>
## Open questions
<bullets>
## Research update
<question; prediction made before evaluation; falsifier; observations; competing explanations;
applicability conditions; supporting/opposing evidence IDs; next discriminating experiment>
## Noise assessment
<practical effect size, comparable items/seeds, uncertainty, replication gaps; no unsupported significance claims>
## Belief revisions
<which earlier scoped claims are challenged, what new evidence says, and what remains undecided>
## Stop or continue
<recommendation and concrete saturation/remaining-gap criteria; the next research round decides globally>
```

# proposals.json schema
A JSON list of 1 to 3 objects, ranked best first:
```
[{"title": "short name", "hypothesis": "what to change and why it should help, concrete enough to implement without you",
  "type": "idea|debug|ablate|scale", "expected_gain": "rough estimate with reasoning", "risk": "what could go wrong"}]
```
Begin by reading `docs/` and $entry_files, then check the quick score of the untouched code so you know your starting point.
For each proposal also include research_question, prediction, falsifier, and evidence_ids (a list).
$proposal_rule
