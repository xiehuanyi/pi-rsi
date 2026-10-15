# Competition mode: climb the official score
This task is run like an ML competition. The objective is the highest official aggregate score at the end of the
campaign: not a mechanistic explanation of why a method works, and not the score of any single segment. Work the
way strong competition teams do:

1. **Every score you use is a proxy; know how good it is.** The real target is out of reach. The official level
   stands in for it, the quick/dev level stands in for the official level, and your delivery rule stands in for
   the dev level; each layer adds noise and bias. Check that dev and official deltas move in the same direction;
   when they disagree, fix the local validation before chasing small dev gains. When a result on the real target
   exists (for example a leaderboard score), compare it with the official score and say what the gap implies for
   the direction you choose.
2. **Error analysis picks the next step.** Break the metric down by every segment the evaluator reports
   (classes, sources, subgroups) and attack the largest recoverable loss per hour of work first. Segments are
   diagnostics that show where score is lost; they are not separate objectives.
3. **Optimize the aggregate; veto only clear harm.** A change that raises the aggregate is a win even when a
   segment moves down inside its own noise. A segment loss counts only when it exceeds about two paired standard
   errors of that segment, pooled over the seeds you ran; then gate, route or blend so the gain survives without
   the loss. A segment of a few dozen items cannot veto anything. Merge independent wins from different branches
   into one pipeline instead of leaving them on separate leaves.
4. **Big levers before fine tuning.** Order of attack: stronger models and representations, better candidate
   generation/features, more and better-used training data, then hyperparameters, then ensembling/blending of
   diverse strong components and test-time aggregation. Use the compute budget when it buys score.
5. **Fast iteration.** Run the smallest experiment that shows whether a lever works (subsample, fewer epochs, one
   segment), then scale the winner to the full budget in the same node. Several quick trials beat one slow one.
6. **Ablations only when they change a decision.** Spend trials on controls to choose between expensive
   directions or to debug a regression, never just to explain a mechanism. No node should exist only to audit or
   explain; every node ships its best-scoring pipeline.
7. **Robust submissions.** Deterministic seeds, finish inside the time cap with margin, always write a valid
   output (fallbacks for every failure path), no use of evaluation labels.
8. **Ship what you test.** The delivery rule for a new component: deliver it switched on when its paired
   development gain in the aggregate metric, pooled over the seeds you ran, is positive and the run is valid
   (integrity, runtime margin, determinism). Do not stack per-segment or per-seed non-decrease conditions on top:
   with k independent checks a real but small gain passes with probability near 0.5^k, and only changes that
   cannot reorder anything get through, which blocks exactly the big levers of rule 4. A component delivered
   switched off is never measured officially, so the study learns nothing from it; the harness already picks the
   best node by official score, which is the safety net against a bad delivery. A stricter condition must cite
   the setup decision that requires it; a setup decision that asks for diagnostics asks for reports, not vetoes.
   When a plan prescribes stricter delivery conditions without such a
   citation, the worker applies this rule and reports what the stricter conditions would have decided.
9. **Noise and forecasts.** Gains inside the official noise band are unproven, not worthless; keep them when the
   pooled aggregate is positive, and prefer directions with large expected effect over polishing within the
   noise. Compare earlier forecasts with the realised official deltas; when they keep missing in the same
   direction, say so, shrink the forecast and change direction instead of repeating it.
10. **Do not stop early.** While budget remains and some direction has positive expected score gain, continue;
   saturation means every remaining lever was tried at full strength, not that the last two nodes stalled.
