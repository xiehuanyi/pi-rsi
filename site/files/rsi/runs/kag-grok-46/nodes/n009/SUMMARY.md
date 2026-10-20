# Summary n009: Skip late DROP while tiles need water

Late DROP (hour≥21) now runs only if the unit has no WATER/HARVEST/PLANT job or no unwatered plants remain; threshold-24 DROP unchanged. Official validation score 22085.88 vs parent 21683 (+403); win_rate 1.0, 0 errors, n=32. Worker quick-set: 22221.7 vs parent 21815.2.

- official score: 22,086 (delta vs parent 402.8, vs best -2,528)
- verdict: improved
- commit: d5d3f811
- claim check: consistent — Handoff validation 22085.9 / margin 18381.6 / win_rate 1.00 / errors 0 / std 242.5 / min 21632 / max 22373 / n=32 matches official 22085.88, 18381.62, 1.0, 0, 242.49, 21632, 22373, 32. Quick 22221.7 and seed-101 $22373 are worker-only, not official validation.

## Git log
```
d5d3f81 Skip hour-21 DROP while a unit still has crop work.
```
```
agent.py         |  2 +-
 src/constants.py |  3 ++-
 src/policy.py    | 33 +++++++++++++++++++++++++++++----
 3 files changed, 32 insertions(+), 6 deletions(-)
```
