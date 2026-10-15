#!/usr/bin/env bash
# End-to-end harness test without any LLM: script runner + fake utility. Exercises planner, failure, diagnoser,
# retry, audit, scheduling, and the final report. Takes ~1-2 minutes (real evaluator runs).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXP="$HERE/experiments/_test_loop"
rm -rf "$EXP"
"$HERE/rsi" init "$EXP" --task "$HERE/tasks/kaggriculture" --runner script --model "$HERE/tests/fake_agent.py" \
  --utility-runner script --utility-model "$HERE/tests/fake_agent.py" --width-root 2 --width 1 --depth 2 --max-nodes 4 \
  --parallel 2 --patience 10 --node-timeout 120 --idle-timeout 60 --name test_loop --no-research-loop --no-maintainer >/dev/null
"$HERE/rsi" run "$EXP" --quiet
"$HERE/rsi" status "$EXP"
python3 - "$EXP" <<'PY'
import json, sys
from pathlib import Path
exp = Path(sys.argv[1])
t = json.loads((exp / "tree.json").read_text())
nodes = {n["id"]: n for n in t["nodes"]}
# A failed execution is retried as a new attempt of the SAME hypothesis (executions/<id>.json), not a new node.
journals = [json.loads(p.read_text()) for p in (exp / "executions").glob("n*.json")]
retried = [j for j in journals if len(j["attempts"]) >= 2]
failed = [a for j in retried for a in j["attempts"][:-1] if a["state"] == "failed"]
done = [n for n in nodes.values() if n["status"] == "done" and n["id"] != "root"]
assert failed, "expected at least one failed attempt (broken agent)"
assert retried, "expected a retried hypothesis"
assert all(nodes[j["node_id"]]["status"] == "done" for j in retried), "retries should succeed"
assert done, "expected done nodes"
assert (exp / "REPORT.md").exists() and (exp / "tree.html").exists() and (exp / "final.json").exists()
assert "fake insight" in (exp / "INSIGHTS.md").read_text()
print("TEST OK:", len(nodes) - 1, "nodes;", len(failed), "failed attempts;", len(retried), "retried;", len(done), "done")
PY
