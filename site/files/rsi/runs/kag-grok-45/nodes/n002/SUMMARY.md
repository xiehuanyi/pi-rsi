# Summary n002: Cheap daily hired hands for parallel farm ops

Daily hired hands (TARGET=6) plus partitioned NW carrot farming raised official validation score from 3587 to 9084.59 (margin 5887.97, win_rate 1.0, 32 games, 0 errors). Worker quick best was 11690.2. Water-before-harvest and no mid-day shed hauls were the key tunings; more/fewer hands and seed stockpiling underperformed on quick.

- official score: 9,085 (delta vs parent 5,498, vs best 5,498)
- verdict: improved
- commit: d48c7758
- claim check: consistent — Handoff validation 9084.6 / margin 5888.0 / std 1877.2 / win_rate 1.0 / errors 0 matches official 9084.59 / 5887.97 / 1877.19 within rounding; git_sha and n_games=32 also align. Quick figures are correctly labeled as quick-set.

## Git log
```
d48c775 n002: tune parallel hands — water-before-harvest, no DROP hauls
50ee233 n002: parallel carrot farm with daily hired hands
```
```
agent.py        |  35 +++-------
 src/farm_ops.py | 194 ++++++++++++++++++++++++++++++++++++++++++++++++++++++++
 src/market.py   |  58 +++++++++++++++++
 src/pathing.py  |  37 +++++++++++
 4 files changed, 299 insertions(+), 25 deletions(-)
```
