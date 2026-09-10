# Spaceship Titanic data (from the competition page)

Predict whether a passenger was transported to another dimension during the Spaceship Titanic's collision with a
spacetime anomaly. Submissions are scored by classification accuracy.

## Files workers see
- `data/train.csv` — public labeled split (a group-aware subset of Kaggle's train). Has `Transported`.
- `data/test.csv` — official Kaggle test features. No labels.
- `data/sample_submission.csv` — `PassengerId,Transported` with `True`/`False`. Match this format.

## Columns
- `PassengerId` — `gggg_pp`. `gggg` is the travel group, `pp` the number within the group. People in a group are often
  family members but not always. Groups frequently share a cabin and have correlated outcomes.
- `HomePlanet` — planet the passenger departed from (typically their permanent residence). Values include Earth,
  Europa, Mars, plus missing.
- `CryoSleep` — whether the passenger elected suspended animation for the voyage; such passengers are confined to
  cabins. Stored as boolean-like values with missings.
- `Cabin` — `deck/num/side`. Deck is a letter (A–G, T), `num` is an integer, side is `P` (Port) or `S` (Starboard).
  Missing cabins occur.
- `Destination` — planet the passenger will debark to (`TRAPPIST-1e`, `55 Cancri e`, `PSO J318.5-22`, plus missing).
- `Age` — age in years (float, missing allowed).
- `VIP` — whether the passenger paid for VIP service (boolean-like, missing allowed).
- `RoomService`, `FoodCourt`, `ShoppingMall`, `Spa`, `VRDeck` — amount billed at each amenity (floats, missing allowed).
- `Name` — first and last names. Last names can hint at families inside a group.
- `Transported` — target, only in the labeled file: whether the passenger was transported (`True`/`False`).

## Notes
- Missingness is common on categoricals, cabin, spend, and CryoSleep. Impute using only the labeled file passed to
  `--train` (plus rules that do not peek at prediction-set labels — there are none).
- The prediction file in `--predict` has the same feature columns as train except it may omit `Transported`.
- Do not join labels for `data/test.csv` from any source.
