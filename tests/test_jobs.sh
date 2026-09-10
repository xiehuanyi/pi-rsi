#!/usr/bin/env bash
# Job-mode end-to-end test without an LLM: toy long-job task, fake agent, queue daemon, analysis session,
# top-k final evaluation. Uses a private jobs dir so it does not touch a real daemon. ~2-3 minutes.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXP="$HERE/experiments/_test_jobs"
export RSI_JOBS_DIR="$HERE/experiments/_test_jobs_queue" RSI_GPUS=""
rm -rf "$EXP" "$RSI_JOBS_DIR"
[ -d "$HERE/pi_rsi/tasks/toy-longjob/.venv" ] || "$HERE/pi_rsi/tasks/toy-longjob/setup.sh" >/dev/null
"$HERE/rsi" init "$EXP" --task "$HERE/pi_rsi/tasks/toy-longjob" --runner script --model "$HERE/tests/fake_agent.py" \
  --utility-runner script --utility-model "$HERE/tests/fake_agent.py" --width-root 2 --width 1 --depth 2 --max-nodes 3 \
  --parallel 2 --patience 10 --node-timeout 120 --idle-timeout 60 --no-narrative --name test_jobs >/dev/null
"$HERE/rsi" run "$EXP" --quiet
"$HERE/rsi" status "$EXP"
"$HERE/rsi" jobs | head -12
python3 - "$EXP" "$RSI_JOBS_DIR" <<'PY'
import json, sys, glob
from pathlib import Path
exp, q = Path(sys.argv[1]), Path(sys.argv[2])
t = json.loads((exp / "tree.json").read_text()); nodes = {n["id"]: n for n in t["nodes"]}
done = [n for n in nodes.values() if n["status"] == "done" and n["id"] != "root"]
assert len(done) >= 2, "expected done nodes"
jobs = [json.loads(p.read_text()) for p in (q / "queue").glob("*.json")]
assert any(j["status"] == "done" for j in jobs), "no finished jobs"
assert all(j["metrics_path"] for j in jobs), "jobs must carry a metrics path"
assert any(j["incumbent_path"] for j in jobs), "later jobs should carry an incumbent curve for early stopping"
final = json.loads((exp / "final.json").read_text())
assert "ranking" in final and len(final["ranking"]) == 2, f"final top-2 ranking missing: {final}"
h = (exp / "nodes" / done[0]["id"] / "HANDOFF.md").read_text()
assert "official result seen by fake analysis" in h, "analysis session did not update the handoff"
# stop a daemon we started
d = json.loads((q / "jobd.json").read_text())
import os, signal
try: os.kill(d["pid"], signal.SIGTERM)
except OSError: pass
print("TEST OK: jobs", len(jobs), "done nodes", len(done), "ranking", final["ranking"])
PY
