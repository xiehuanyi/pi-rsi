"""Kaggriculture agent — entry point. The evaluator imports `agent(obs)` from this file.

Starting point: the official starter policy (a single carrot loop on the farmer's tile). Everything else is up to you.
Helpers belong in src/ (importable because the evaluator puts this directory on sys.path).
"""
from __future__ import annotations

from src.constants import CROPS


def agent(obs: dict) -> dict:
    """Carrot loop: buy one carrot seed, plant on the current tile, water daily, harvest at max_yield_day, sell."""
    farms = obs.get("farms", [])
    player = obs.get("player", 0)
    private = obs.get("private", {}) or {}
    if not farms or player >= len(farms):
        return {"farmer": ["PASS"], "hands": [], "market": []}
    farm = farms[player]
    fx, fy = farm["farmer"]
    tile = farm["tiles"][fy][fx]
    day = obs.get("day", 0)
    seeds = private.get("seeds", {})
    shed = private.get("shed", {})

    market = []
    if shed.get("CARROT", 0) > 0:
        market.append(["SELL", "CARROT", shed["CARROT"]])
    if seeds.get("CARROT", 0) == 0 and farm["money"] >= CROPS["CARROT"]["seed"]:
        market.append(["BUY_SEED", "CARROT", 1])

    farmer = ["PASS"]
    if tile is None and seeds.get("CARROT", 0) > 0:
        farmer = ["PLANT", "CARROT"]
    elif isinstance(tile, dict) and tile.get("kind") == "PLANT" and tile["crop"] == "CARROT":
        age = day - tile["planted_day"]
        if age >= CROPS["CARROT"]["max_yield_day"]:
            farmer = ["HARVEST"]
        elif not tile["watered_today"]:
            farmer = ["WATER"]
    return {"farmer": farmer, "hands": [], "market": market}
