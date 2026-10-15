#!/usr/bin/env python3
"""Create an isolated local Kaggriculture duel task from the user's archived controllers."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def put(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", type=Path, required=True, help="existing Kaggriculture project")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    archive, dest = a.archive.resolve(), a.out.resolve()
    if dest.exists():
        raise SystemExit("destination already exists; create a new version")
    legacy = ROOT / "pi_rsi/tasks/kaggriculture"
    ev, docs, starter = dest / "eval", dest / "docs", dest / "starter"
    for p in (ev / "opponents", docs, starter / "src"):
        p.mkdir(parents=True)
    for name in ("GETTING_STARTED.md", "RULES.md", "kaggriculture.spec.json", "NOTICE.md"):
        shutil.copy2(legacy / "docs" / name, docs / name)
    v45 = archive / "variants/v45_current.py"
    shutil.copy2(v45, docs / "v45_base.py")
    shutil.copy2(v45, ev / "opponents/v45.py")
    shutil.copy2(archive / "main.py", ev / "opponents/v47.py")
    sources = {"v45": {"path": str(v45), "sha256": sha(v45)},
               "v47": {"path": str(archive / "main.py"), "sha256": sha(archive / "main.py")}}
    # Unique package names prevent candidate/opponent src imports and globals from colliding.
    melon = ROOT / "experiments/kag-grok-45/worktrees/n008"
    prefix = "frozen_melon_src"
    for p in [melon / "agent.py", *sorted((melon / "src").rglob("*.py"))]:
        rel = Path("melon.py") if p.name == "agent.py" else Path(prefix) / p.relative_to(melon / "src")
        text = re.sub(r"\bfrom src\b", "from " + prefix, p.read_text())
        text = re.sub(r"\bsrc\.", prefix + ".", text)
        put(ev / "opponents" / rel, text)
    sources["melon"] = {"path": str(melon), "commit": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=melon, text=True).strip()}
    bundle = archive / "deployment/berry_completion/submission.tar.gz"
    sources["berry"] = {"path": str(bundle), "sha256": sha(bundle)}
    with tarfile.open(bundle) as tar:
        for member in tar.getmembers():
            if not member.isfile() or not member.name.endswith(".py"):
                continue
            rel = Path(member.name)
            if rel.is_absolute() or ".." in rel.parts or rel.parts[0] not in ("main.py", "src"):
                raise ValueError("unexpected archive path")
            rel = Path("berry.py") if rel.name == "main.py" else Path("frozen_berry_src") / Path(*rel.parts[1:])
            text = tar.extractfile(member).read().decode()
            text = re.sub(r"\bfrom src\b", "from frozen_berry_src", text)
            text = re.sub(r"\bsrc\.", "frozen_berry_src.", text)
            put(ev / "opponents" / rel, text)
    # Reuse the previously confirmed procurement repair without importing analysis/replay tooling.
    source = (archive / "src/v45_hire_guard.py").read_text()
    function = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "protect_procurement")
    put(starter / "src/procurement.py", '"""Preserve non-sale orders under the 10-order cap."""\n'
        "CAP = 10\ndef is_sell(order):\n    return isinstance(order, list) and order and order[0] == 'SELL'\n\n"
        + ast.unparse(function) + "\n")
    source = (archive / "src/v45_guard_agent.py").read_text()
    function = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "_bind_animal_guard")
    put(starter / "src/baseline.py",
        '"""Archived V45 plus the previously corroborated animal-overlay procurement repair."""\n'
        "import importlib.util\nfrom pathlib import Path\nimport sys\n"
        "from src.procurement import protect_procurement\n\n"
        + ast.unparse(function) + "\n\n"
        "_path = Path(__file__).resolve().parents[1] / 'docs/v45_base.py'\n"
        "_spec = importlib.util.spec_from_file_location('_archived_v45', _path)\n"
        "baseline = importlib.util.module_from_spec(_spec)\n"
        "sys.modules[_spec.name] = baseline\n_spec.loader.exec_module(baseline)\n"
        "_bind_animal_guard(baseline)\n")
    put(starter / "src/__init__.py", "")
    put(starter / "src/policy.py",
        '"""Research interventions go here; start from the retained repaired V45 controller."""\n'
        "from src.baseline import baseline\n\n"
        "def act(obs):\n    return baseline.agent(obs)\n")
    put(starter / "agent.py", "from src.policy import act\n\ndef agent(obs):\n    return act(obs)\n")
    # Local standalone starter also carries its immutable baseline for preflight evaluation.
    shutil.copytree(docs, starter / "docs")
    shutil.copy2(ROOT / "pi_rsi/duel_eval.py", ev / "eval.py")
    runtime = legacy / ".venv"
    (dest / ".venv").symlink_to(runtime, target_is_directory=True)
    metadata = json.loads(subprocess.check_output([str(runtime / "bin/python"), "-c",
        "import importlib.metadata as m,json,hashlib;d=m.distribution('kaggle-environments');"
        "p=d.locate_file('kaggle_environments/envs/kaggriculture/kaggriculture.py');"
        "print(json.dumps({'version':d.version,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}))"], text=True))
    protocol = {
        "environment_version": metadata["version"], "engine_sha256": metadata["sha256"],
        "baseline_sha256": sha(v45), "baseline": "archived V45 + prior animal procurement repair",
        "sources": sources, "metric": "mean_win_plus_half_draw", "role": "exploratory_selection",
        "opponents": {n: f"opponents/{n}.py" for n in ("v45", "v47", "melon", "berry")},
        "opponent_files": {str(p.relative_to(ev)): sha(p) for p in sorted((ev / "opponents").rglob("*.py"))},
        "seeds": {"smoke": [1103], "quick": [1103, 1117],
                  "validation": [2203, 2213, 2221, 2237, 2243, 2251],
                  "confirmation": [3301, 3307, 3313, 3319, 3323, 3329, 3331, 3343,
                                   3347, 3359, 3361, 3371]},
    }
    protocol["id"] = "duel-v1-" + hashlib.sha256(json.dumps(protocol, sort_keys=True).encode()).hexdigest()[:16]
    put(ev / "protocol.json", json.dumps(protocol, indent=2) + "\n")
    put(dest / "task.toml", """[task]
name = "kaggriculture-duel-v1"
brief = "TASK.md"
docs = ["docs/RULES.md", "docs/GETTING_STARTED.md", "docs/kaggriculture.spec.json", "docs/BASELINE.md", "docs/v45_base.py"]
python = ".venv/bin/python"

[eval]
eval_command = "{python} {task_dir}/eval/eval.py --agent-dir {worktree} --seedset {seedset} --out {out} --workers 4 --quiet"
worker_eval_command = "{python} eval/eval.py --seedset {seedset} --workers 4"
worker_val_command = ""
seedsets = ["smoke", "quick", "validation", "confirmation"]
official_seedset = "validation"
quick_seedset = "quick"
final_seedset = ""
eval_timeout_s = 1200
higher_is_better = true
score_key = "score"
""")
    put(dest / "TASK.md", """# Kaggriculture: fixed-opponent outcome research

Improve mean(win + 0.5*draw) across four equally weighted archived controllers,
fixed random seeds and both seats. This is a local exploratory panel, not live leaderboard rating.
Start from archived V45 plus its previously corroborated animal-overlay procurement repair.
Keep the archived base immutable; add ONE intervention in src/ per node.

## Why
Earlier mean-money-vs-starter optimization did not establish competitive win-rate gains.
The market is shared, so a production or sale policy may help against one economy and hurt another.
Research conditional mechanisms using outcome, per-opponent results, money, and action diagnostics.
Do not select by money margin when outcome is unchanged.

## Protocol
quick: 2 seeds x 2 seats x 4 opponents = 16 games. Iterate here.
validation: 6 different seeds x 2 seats x 4 opponents = 48 games, computed by the harness.
Confirmation seeds are reserved for one locked candidate AFTER search; do not run them or
use their results to re-plan. No automatic external submission or final-level run is configured.
Per-item uncertainty blocks include ALL opponents and both seats for a seed.
The four controllers are our archived V45, V47, berry controller and pi-rsi melon winner.
They are correlated and incomplete coverage of the live population. Do not claim promotion.

## Working contract
agent.py exposes agent(obs). It imports src/policy.py; src/baseline.py loads docs/v45_base.py
and installs the retained procurement repair. You may modify src/ and agent.py.
Frozen eval/ and docs/ must not change. The vendored archived base is exempt from the
400-line limit; new research modules must remain below 400 lines.
Use only the game observation at runtime, no opponent IDs, replays, private data, network,
or future actions. Do not inspect confirmation outcomes. Log requested actions as requested,
not as accepted operations. Per-opponent failures invalidate evidence; candidate failures lose.

Do not repeat the completed hire-guard experiment or prior unsuccessful CARE, assignment,
composition and static sell-threshold sweeps. Use those as conditional prior evidence.
Prefer a new discriminating market mechanism or a diagnostic explaining outcome failures.
State predictions and falsifiers before evaluating. Preserve evidence IDs in the handoff.
""")
    put(docs / "BASELINE.md", """# Archived baseline and transferred experience

The base is V45 from variants/v45_current.py, not the Kaggle project's main.py (which is V47).
It uses a fixed farm action route with observation-conditioned market and repair overlays.
src/baseline.py adds the existing procurement repair to the animal-competition overlay.
That repair previously improved bank money against an animal-heavy proxy without changing
win/loss counts. It is a retained starting repair, not evidence of increased competitive win rate.

Useful base functions (read function bodies, skip the compressed route data):
_projected_shed, _opponent_exposure, _ranked_sells, _front_run_market,
_animal_competition_market, _hybrid_action, agent.
_ranked_sells is redefined near the file end: the LAST definition is active.
The base module is available as src.baseline.baseline; monkey-patching one function is possible.
Preserve the retained route unless a specific measured failure requires changing it.

Prior pi-rsi crop-only runs discovered crop-specific land payoffs, conditional locality effects,
and fertilizer-vs-eggs confounding. Their numerical scores were mean bank against starter
and cannot be compared with this win/draw/loss metric.
The older Kaggle audit found requested/executed sales differ substantially; do not calibrate
supply from requested SELL quantities as though all orders executed.
Archive source hashes and environment identity are recorded in eval/protocol.json.
""")
    shutil.copy2(docs / "BASELINE.md", starter / "docs/BASELINE.md")
    put(dest / "PROVENANCE.json", json.dumps({"protocol": protocol["id"], "sources": sources}, indent=2) + "\n")
    print(json.dumps({"task": str(dest), "protocol": protocol["id"], "opponents": list(protocol["opponents"])}, indent=2))


if __name__ == "__main__":
    main()
