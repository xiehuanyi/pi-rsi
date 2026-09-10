The official `$level` run for your node `$node_id` has finished. This is the result the harness will record:

- official score (`$score_key`, $direction): $score
- parent's official score: $parent_score; global best before this node: $best_score; baseline: $root_score
- run summary: $run_summary

Curve (step, value) samples from the official run:
$curve

Update `$node_dir/HANDOFF.md` and `$node_dir/proposals.json` in place so they reflect this official result:
the Result section must quote the official number (labelled official) next to your quick-set numbers; revise the
Mechanism, Dead ends and Next hypotheses sections if the official result changes the picture. Do not change code and
do not run anything except reading files. Keep both files in the required schemas. Then stop.
