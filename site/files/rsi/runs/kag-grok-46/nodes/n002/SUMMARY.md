# Summary n002: Early daily HIRE to multiply plant/water throughput

Replaced solo carrot loop with morning HIRE of 5 hands (Fibonacci ~$12/day) plus WHEAT on the NW 5×5, stay-on-tile plant/water/harvest/sell. Official validation score 16216.75 (parent ~3587; margin 12609.25; win_rate 1.0; n=32; errors 0). Worker quick-set: 15888.33 vs untouched 3491.3.

- official score: 16,217 (delta vs parent 12,630, vs best 12,630)
- verdict: improved
- commit: da8b7b89
- claim check: consistent — Handoff validation score 16216.75, margin 12609.25, win_rate 1.0, n=32, errors 0, std 1207.65, min/max 15064/18375, and git_sha match official metrics; quick 15888.33 is correctly labeled as worker quick-set.

## Git log
```
da8b7b8 Comment why units finish the current tile before walking.
8652bbe Hire 5 hands each morning and tend wheat across the NW field.
```
```
agent.py         |  47 ++++-------
 src/constants.py |  29 +++++++
 src/grid.py      |  89 ++++++++++++++++++++
 src/policy.py    | 248 +++++++++++++++++++++++++++++++++++++++++++++++++++++++
 4 files changed, 381 insertions(+), 32 deletions(-)
```
