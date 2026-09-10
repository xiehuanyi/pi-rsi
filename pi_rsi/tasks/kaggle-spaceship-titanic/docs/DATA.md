# Spaceship Titanic data (from the competition page)

Predict whether a passenger was transported to another dimension during the Spaceship Titanic's collision with a
spacetime anomaly.

- `PassengerId` — `gggg_pp`: gggg is the travel group, pp the number within the group. People in a group are often
  family members but not always.
- `HomePlanet` — planet the passenger departed from (typically their permanent residence).
- `CryoSleep` — whether the passenger elected suspended animation for the voyage; such passengers are confined to cabins.
- `Cabin` — `deck/num/side`, side is `P` (Port) or `S` (Starboard).
- `Destination` — planet the passenger will debark to.
- `Age`, `VIP` — age; whether the passenger paid for VIP service.
- `RoomService`, `FoodCourt`, `ShoppingMall`, `Spa`, `VRDeck` — amount billed at each amenity.
- `Name` — first and last names.
- `Transported` — target: whether the passenger was transported (True/False).

Submissions are scored by classification accuracy.
