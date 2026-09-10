#!/usr/bin/env bash
# Verifies the pi runner end to end against a local mock OpenAI server (no API key needed).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT=$(python3 -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',0)); print(s.getsockname()[1])")
TMP=$(mktemp -d)
python3 "$HERE/tests/mock_openai.py" "$PORT" & MOCK=$!
trap 'kill $MOCK 2>/dev/null; rm -rf "$TMP"' EXIT
mkdir -p "$TMP/agentdir" "$TMP/work" "$TMP/logs"
cat > "$TMP/agentdir/models.json" <<JSON
{"providers": {"mock": {"baseUrl": "http://127.0.0.1:$PORT/v1", "api": "openai-completions", "apiKey": "x",
  "models": [{"id": "mock-1", "contextWindow": 32000, "maxTokens": 4096}]}}}
JSON
sleep 1
cd "$HERE" && PI_CODING_AGENT_DIR="$TMP/agentdir" PYTHONPATH="$HERE" python3 - "$TMP" <<'PY'
import sys
from pathlib import Path
from pi_rsi.runner import make_runner
tmp = Path(sys.argv[1])
r = make_runner("pi", "mock/mock-1", "")
res = r.run_agent("Write hello to out.txt using bash, then say DONE.", cwd=tmp / "work", log_path=tmp / "logs" / "pi.jsonl",
                  max_turns=5, timeout_s=120, idle_timeout_s=60)
print("ok", res.ok, "exit", res.exit_code, "text", repr(res.final_text), "tools", res.tool_calls, "usage", res.usage, "err", res.error)
out = (tmp / "work" / "out.txt")
assert out.exists() and out.read_text().strip() == "hello-from-mock", "tool call did not run"
assert "DONE mock" in res.final_text, "final text not captured"
assert res.tool_calls == 1
print("TEST OK: pi runner executed a tool call and captured the final message")
PY
