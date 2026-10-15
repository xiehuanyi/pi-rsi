
# Delivery declaration
Before you finish, write `$node_dir/DELIVERY.json`, one object saying what the delivered commit runs:
```
{"component": "on" | "off" | "none",
 "active_commit": "<full hash of a commit on this branch where the new component runs switched on; required for off>",
 "dev_delta": <paired development gain of the switched-on component over the parent in the aggregate metric,
               pooled over the seeds you ran, or null>,
 "dev_sem": <its paired standard error, or null>,
 "reason": "<one or two sentences>"}
```
`on`: the delivered commit runs the new component. `off`: you switched it off; the harness then measures
`active_commit` officially instead, because a switched-off component teaches the study nothing. `none`: this
node delivers no new component (a diagnostic, or nothing could be made to run). Commit the switched-on state
before switching it off so that `active_commit` exists.

Tuning trials are counted by distinct trial number in TUNING.jsonl: a rerun of a trial that crashed before
producing a result keeps its number, and a failure or correction is recorded as a row with an "event" field.
