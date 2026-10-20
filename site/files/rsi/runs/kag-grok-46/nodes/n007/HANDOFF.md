# Handoff n007: Defer goose CARE on harvest days
## Hypothesis
On days with many ripe wheat tiles, skip CARE and egg HARVEST (keep FEED+COLLECT) so all 9 actors stay on the 4-step harvest chain. Seed 101 still left 4–10 tiles unwatered at hour 23; missed waters become weeds and lost cycles. CARE roughly doubles eggs (~+$40/goose/day) but a missed 4-wheat tile is ~$80 plus a desynced replant.
## What I did
- `src/constants.py`: `GOOSE_MAX_HELD`, `HARVEST_DAY_RIPE_MIN=8`, `HARVEST_DAY_COHORT_MIN=18`.
- `src/animals.py`: `is_wheat_harvest_day` latches a harvest wave via still-ripe plants plus same-day replants (so the flag survives after the cohort is cut, without cross-turn state). `should_defer_care` is that latch AND `wheat_chain_busy` (unwatered / ripe / plantable empty). While deferring: skip CARE and non-cap egg HARVEST and egg-walk jobs; keep FEED, COLLECT, BUILD/PLACE, and drain eggs at `max_held=4`. DROP visitors with a harvest load skip coop actions. `needed_pickup` wheat-for-feed is allowed only for the unit assigned to the coop (`target==pos`) on those days.
- `src/policy.py`: `choose_unit_actions` computes `defer_care` and threads it into `animal_jobs`, `standing_animal_action`, and `needed_pickup`.
- `agent.py`: still `agent(obs) -> decide(obs)` with fail-closed PASS.
## Result
- untouched quick: score 23286.6 (12 games, errors=0). Command: `eval/eval.py --seedset quick`
- v5 quick: score 23665.8 (was 23286.6); margin 20068.1; win_rate 1.00; errors 0; std 514.3; min 23011 max 24566. Command: `eval/eval.py --seedset quick`
- validation: score 24088.0 (was 23597.9 at n005); margin 20525.8; win_rate 1.00; errors 0; std 765.3; min 23278 max 26443; n_games 32. Command: `eval/eval.py --seedset validation`
- git: `db7d14ace4be13287f679d31db9edeec3b29b929`
## Mechanism
Coops sit on the shed-access spawn tiles, so harvest DROP walks land on geese. Skipping CARE/egg HARVEST on a latched harvest day frees those actors for water→harvest→replant→water, but only if DROP visitors are not allowed to PICKUP 1 wheat and FEED (that was a no-op that ate the slack). FEED+COLLECT still run on the assigned coop actor, so fertilizer and feeding continue. CARE still runs on watering-only days and after a harvest wave actually finishes, so most egg bonuses remain. Peak leftovers shrank on several days (seed 101 day 17/21 went 3–6 unwatered → 0) but 5–7 unwatered tiles remain on the heaviest waves.
## Dead ends
- v1 skip CARE whenever any wheat work remains (every morning is unwatered): seed 101 21693, quick 21879.6. CARE never ran on harvest days that never finished; extra FEED no-ops (4–6 vs 2).
- v2 exclusive one-unit-per-coop-tile plus harvest latch: seed 101 18019, quick 17871.4. Occupant COLLECTs fertilizer and leaves to FERTILIZE before CARE; nobody else is allowed to CARE. Leftovers worse (11–13). Same class as n005 assigned-only coops.
- v3 harvest-day skip without blocking visitor feed pickup: seed 101 22713, quick 22989.4. CARE/eHARV went to 0 on peak days as intended, but leftovers stayed 6–7 and FEED rose to 4–6 (DROP visitors feeding harvested wheat). Egg income dropped, waters did not close.
- v4 skip coop actions when carrying wheat>1 / inventory>=12: identical to v3. Extra FEED is 1-wheat shed pickups after DROP, not harvest loads.
## Next hypotheses
- Route DROP/PICKUP to locked SW/SE shed tiles (4,5) and (5,5) so harvest dumps never stand on goose coops; leftover waters are still 5–7 on peak days and DROP-on-coop is the remaining collision.
- Compact spawn-aware regions on the 5×10 NW+NE strip so locked SW/SE spawn tiles waste fewer morning walks and the remaining harvest leftovers close.
- Hire a 9th hand on harvest-cohort days only (fib $34) to finish 5–7 unwatered leftovers without paying the fee on watering-only days.
## Open questions
- Seed 101 seat 0 is still slightly below parent (23011 vs 23453) while the seed set mean rose; is 101’s leftover-7 on day 8 a DROP-walk issue the latch does not catch?
- Two fertilizer/day still covers only ~2 of ~10 plants entering the age-2 window; how much of the +$490 validation gain is extra wheat vs fewer weeds vs eggs that still sell after deferred harvest?
- Last plant day is 25; day 28–29 leftover ripe plants and last-day EOD shed wheat may still miss a SELL turn.
