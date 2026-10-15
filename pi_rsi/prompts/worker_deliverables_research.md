9. Finish by writing `$node_dir/IMPLEMENTATION.md` (schema below). It is mandatory; if you are out of budget, a short one beats none.

# IMPLEMENTATION.md schema (markdown, keep these exact section headers)
It records what you did, nothing else. You will not see the official result: do not interpret it, judge the
hypothesis, or plan next steps. After the official evaluation the research lead writes HANDOFF.md (what the
result means) and NEXT.md (what to do next), citing this file instead of repeating it.
```
# Implementation $node_id: <title>
## What I built
<bullets; name the files/functions changed and the final git commit>
## How to run
<the exact command(s) that reproduce the delivered model>
## Development results
<quick-set numbers with seed set and command; they are development evidence, not official results>
## Tuning
<trials from TUNING.jsonl and the configuration kept, with the reason>
## Known issues
<bugs, shortcuts, deviations from the decision, anything that could mislead a reader of the official score>
```
Begin by reading `docs/` and $entry_files, then check the quick score of the untouched code so you know your starting point.
