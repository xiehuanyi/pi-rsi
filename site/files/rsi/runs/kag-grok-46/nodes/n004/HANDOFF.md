# Handoff n004: Fertilize wheat bonus window via geese
## Hypothesis
Wheat watering alone caps at yield 4; fertilizer during ages 2–4 doubles the daily bonus so the plant hits max_yield 6. One FERTILIZE at age 2 or 3 covers at least two bonus days, which is enough to hit the cap. Bought fertilizer at ~$100 costs more than the extra 2 wheat (~$44 at glut), so the working path is 2–3 geese (coop + $300, feed with own wheat) for free daily fertilizer plus eggs.
## What I did
- `src/constants.py`: `N_GEESE=3`, `GOOSE_TILES=(4,4)/(3,4)/(4,3)`, wheat feed reserve, do-not-sell fertilizer/animals.
- `src/livestock.py`: fertilizer window (`wants_fertilizer` ages 2–3), goose tile ops (BUILD_COOP, PLACE, FEED, COLLECT_FERTILIZER, HARVEST eggs, CARE).
- `src/market.py`: morning HIRE as in n002; BUY_ANIMAL GOOSE until 3; BUY_PRODUCT WHEAT only before day 4 (own harvest has not landed yet); SELL eggs and extra wheat, never fertilizer/geese.
- `src/policy.py`: stay-on-tile wheat loop plus goose jobs; FERTILIZE after WATER when the actor is carrying fertilizer; forced morning PICKUP of wheat/geese/fertilizer from shed-adjacent tiles so field jobs do not starve logistics.
- `src/grid.py`: `inv_get` / `total_item`.
- Did **not** buy $100 fertilizer: 2 extra wheat at glut prices does not pay for it.
## Result
- untouched quick: score 15888.3 (12 games, errors=0)
- quick: score 21822.08 (was 15888.3); margin 18356.33; win_rate 1.00; errors 0; std 1774.3; min 19448 max 24072. Command: `eval/eval.py --seedset quick`
- validation: score 20735.5 (was 16216.75); margin 17165.53; win_rate 1.00; errors 0; std 1884.07; min 18325 max 24975; n_games 32. Command: `eval/eval.py --seedset validation`
- git: `8123f990b5fa5a3554da93186ea0c42f05d4acb0`
## Mechanism
Three geese placed on day 0 produce 1 fertilizer/day each (collected into inventory, then applied). FERTILIZE sets `fertilized_until_day = day+2`, so one unit at age 2 or 3 covers two of the three bonus watering days and lifts wheat from 4 to 6 units. Geese also yield eggs (CARE banks +1, paid on the next daily production) which sell on a glut-tolerant log curve; seed 101 sold 144 eggs and applied 76 fertilizer. Three wheat tiles are sacrificed for coops and ~3 wheat/day go to feed, but egg income plus +2 wheat/fertilized plant more than covers that. Bought fertilizer was skipped: $100 vs ~$44 of extra wheat is negative ROI once we dump a field of wheat.
## Dead ends
- Bought-fertilizer path was not run as a full eval: at wheat ~$22, +2 units return ~$44 against a $100 buy, so it would lose money. Early smoke that crashed on `None.get` for empty goose tiles made the fail-closed agent idle at $3000 for the whole game.
- First working fert pass (collect into shed, no forced pickup) left fertilizer sitting in the shed while all 6 actors watered wheat; seed 101 $15489, below parent. Forced morning PICKUP was required for FERTILIZE to actually fire.
- The (3,4) goose was late/unfed while PLACE sat at the lowest job priority under PLANT; raising BUILD_COOP/PLACE above PLANT placed all 3 geese on day 0.
## Next hypotheses
- Buy NE (then SW) once the bank exceeds ~$4000 and run the same wheat + goose-fertilizer loop on 50 tiles; hire 6–8 hands (next fib costs 8, 13) so harvest-day 4-step chains still finish.
- Add 2–3 more geese on the new land so fertilizer covers the whole field each 5-day cycle (currently ~76 apply / ~132 plant-cycles) and egg volume scales.
- Mix carrots (4-day cycle, pet-cafe hinge demand) on a subset of tiles while keeping fertilized wheat as the glut-tolerant bulk crop.
## Open questions
- Harvest days still steal a goose-CARE turn ((4,3) often unfed/uncared on age-4 days); does skipping CARE on harvest days lose more egg bonus than it saves in wheat?
- Same-day DROP + SELL of eggs/wheat into town ticks (every 4 turns) vs EOD drop + next-morning SELL.
- Last plant day is still 25; leftover ripe plants on day 28–29 are not always collected.
