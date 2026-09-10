#!/usr/bin/env bash
# End-to-end harness test without any LLM: script runner + fake utility. Exercises planner, failure, diagnoser,
# retry, audit, scheduling, and the final report. Takes ~1-2 minutes (real evaluator runs).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXP="$HERE/experiments/_test_loop"
rm -rf "$EXP"
"$HERE/rsi" init "$EXP" --task "$HERE/tasks/kaggriculture" --runner script --model "$HERE/tests/fake_agent.py" \
  --utility-runner script --utility-model "$HERE/tests/fake_agent.py" --width-root 2 --width 1 --depth 2 --max-nodes 4 \
  --parallel 2 --patience 10 --node-timeout 120 --idle-timeout 60 --name test_loop >/dev/null
"$HERE/rsi" run "$EXP" --quiet
"$HERE/rsi" status "$EXP"
python3 - "$EXP" <<'PY'
import json, sys
from pathlib import Path
exp = Path(sys.argv[1])
t = json.loads((exp / "tree.json").read_text())
nodes = {n["id"]: n for n in t["nodes"]}
failed = [n for n in nodes.values() if n["status"] == "failed"]
retries = [n for n in nodes.values() if n.get("retry_of")]
done = [n for n in nodes.values() if n["status"] == "done" and n["id"] != "root"]
assert failed, "expected at least one failed node (broken agent)"
assert retries, "expected a retry node"
assert all(r["status"] == "done" for r in retries), "retries should succeed"
assert done, "expected done nodes"
assert (exp / "REPORT.md").exists() and (exp / "tree.html").exists() and (exp / "final.json").exists()
assert "fake insight" in (exp / "INSIGHTS.md").read_text()
print("TEST OK:", len(nodes) - 1, "nodes;", len(failed), "failed;", len(retries), "retries;", len(done), "done")
PY
