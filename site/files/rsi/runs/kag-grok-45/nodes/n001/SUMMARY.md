# Summary n001: Multi-tile wheat field with daily route

Replaced single-tile carrot with a 20-tile NW wheat farmer (bulk seeds, nearest-work: water>weeds>harvest≥2>plant). Official validation score 8176.69 vs parent 3587 (margin 4575.28, win_rate 1.0, n=32, errors 0). Worker quick-set peaked at 8714.8; smaller fields, age-3/4, and plant-gating scored lower on quick.

- official score: 8,177 (delta vs parent 4,590, vs best -907.9)
- verdict: improved
- commit: cbbf61d7
- claim check: consistent — Handoff validation 8176.7, win_rate 1.00, errors 0, std 920.9, margin 4575.3, and sha cbbf61d match official metrics (8176.69 / 1.0 / 0 / 920.86 / 4575.28). Quick 8714.8 is correctly labeled as quick-set and matches the progress log.

## Git log
```
cbbf61d Keep best multi-tile wheat agent (20 tiles, age>=2 harvest)
a0655c8 Cleaner 15-tile serpentine wheat policy with replant/DROP fixes
09fb037 Harvest wheat at age 3 on 20-tile field
6960820 Full 25-tile NW wheat field; force late-season DROP to sell
e39a79d Harvest wheat at age 4 on 10-tile field for higher yield
72ae978 Only gate planting on urgent_water emptiness
af57bcb Restore best quick-scoring wheat agent (5f5e2b2)
a8390f2 Surgical fix: never plant while urgent watering owed
916df49 Scale field to 16 tiles with replant/DROP fixes
c46cb91 Replant after harvest; batch DROP; water age-1 idle days
fbfa222 Cap wheat field at 8 tiles to avoid synced weed deaths
7d45141 Fix plant-before-water bug; gate optional watering
30e2002 Compact 3x3 wheat block near shed with urgent-water priority
3ee2ec7 Route-based 10-tile wheat field with daily watering
700c145 Tighten wheat field to 12 tiles with water-before-plant discipline
5f5e2b2 Implement multi-tile NW wheat field agent (~20 tiles)
```
```
agent.py       |  38 ++-------------
 src/farm.py    | 131 ++++++++++++++++++++++++++++++++++++++++++++++++++
 src/pathing.py |  22 +++++++++
 src/policy.py  | 149 +++++++++++++++++++++++++++++++++++++++++++++++++++++++++
 4 files changed, 307 insertions(+), 33 deletions(-)
```
