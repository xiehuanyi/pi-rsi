#!/usr/bin/env python3
"""ARC-AGI-2 data layout for the task pack.

- data/training/*.json            1000 public training tasks (inputs + outputs), visible to workers
- data/evaluation_inputs/*.json   120 public evaluation tasks with test outputs REMOVED, visible to workers
- private/evaluation/*.json       the same 120 tasks with test outputs (hidden; scored by the frozen wrapper)
- eval/subsets.json               fixed task-id subsets per level: smoke (10), proxy (40), full (120)
Source: the official ARC-AGI-2 repository checkout (commit f3283f7) on this machine.
"""
from __future__ import annotations

import json
import random
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = Path("/media/xieh0a/data/datasets/ARC-AGI-2/data")


def main() -> int:
    if not (SRC / "training").exists():
        print(f"ARC-AGI-2 data not found at {SRC}; clone https://github.com/arcprize/ARC-AGI-2 there", file=sys.stderr)
        return 1
    tr, evi, priv = HERE / "data" / "training", HERE / "data" / "evaluation_inputs", HERE / "private" / "evaluation"
    for d in (tr, evi, priv):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
    for f in sorted((SRC / "training").glob("*.json")):
        shutil.copy2(f, tr / f.name)
    ids = []
    for f in sorted((SRC / "evaluation").glob("*.json")):
        task = json.loads(f.read_text())
        shutil.copy2(f, priv / f.name)
        stripped = {"train": task["train"], "test": [{"input": t["input"]} for t in task["test"]]}
        (evi / f.name).write_text(json.dumps(stripped))
        ids.append(f.stem)
    rng = random.Random(20260910)
    order = ids[:]
    rng.shuffle(order)
    subsets = {"proxy": sorted(order[:40]), "smoke": sorted(order[40:50]), "full": sorted(ids)}
    (HERE / "eval").mkdir(exist_ok=True)
    (HERE / "eval" / "subsets.json").write_text(json.dumps(subsets, indent=1))
    print(f"training {len(list(tr.glob('*.json')))} tasks; evaluation {len(ids)} tasks; subsets smoke={len(subsets['smoke'])} proxy={len(subsets['proxy'])} full={len(subsets['full'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
