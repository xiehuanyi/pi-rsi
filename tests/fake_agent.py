#!/usr/bin/env python3
"""Deterministic stand-in for an LLM agent, used by tests/test_loop.sh via the `script` runner.

Usage: fake_agent.py <prompt_file> <mode>   (mode: agent | resume | json)
- agent: reads the prompt; on a first attempt it writes a broken agent.py (to trigger eval failure -> diagnoser -> retry);
  on a retry it restores a valid agent.py, writes PROGRESS/HANDOFF/proposals and commits.
- json: answers planner/auditor/diagnoser prompts with canned structured output.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

prompt_file, mode = sys.argv[1], sys.argv[2]
prompt = Path(prompt_file).read_text()


def end(structured=None):
    print(json.dumps({"type": "end", "stopReason": "end_turn", "structuredOutput": structured,
                      "usage": {"input_tokens": 100, "output_tokens": 10}}))


if mode == "json":
    if "planner" in prompt.lower():
        k = int(re.search(r"propose\s+(\d+)", prompt, re.I).group(1)) if re.search(r"propose\s+(\d+)", prompt, re.I) else 2
        end({"proposals": [{"title": f"fake idea {i}", "hypothesis": f"do fake thing {i}", "type": "idea",
                            "expected_gain": "none", "risk": "none"} for i in range(1, k + 1)]})
    elif "auditor" in prompt.lower():
        end({"summary": "fake audit summary", "verdict": "no_change", "insights": ["fake insight"], "deadends": [],
             "claim_check": {"consistent": True, "note": "fake"}})
    elif "diagnoser" in prompt.lower():
        end({"cause": "fake cause", "retry": True, "advice": "fake advice: write a valid agent"})
    elif "writer" in prompt.lower():
        print(json.dumps({"type": "text", "data": "fake narrative paragraph."}))
        end()
    else:
        end({})
    sys.exit(0)

node_dir = Path(re.search(r"Node notes directory.*?`([^`]+)`", prompt).group(1))
node_id = re.search(r"- Node: `([^`]+)`", prompt).group(1)
retry = "this is a retry" in prompt.lower()
node_dir.mkdir(parents=True, exist_ok=True)
with open(node_dir / "PROGRESS.md", "a") as f:
    f.write(f"# Progress {node_id}\n- fake worker start (retry={retry})\n")
print(json.dumps({"type": "text", "data": f"fake worker on {node_id}, retry={retry}"}))
if not retry:
    Path("agent.py").write_text("def agent(obs):\n    return {'farmer': ['PASS'] 'hands': [], 'market': []}\n")  # syntax error
    subprocess.run(["git", "commit", "-qam", "fake: break agent"], check=False)
else:
    subprocess.run(["git", "checkout", "-q", "rsi/root", "--", "agent.py"], check=False)
    Path("agent.py").write_text(Path("agent.py").read_text() + "\n# fake tweak\n")
    subprocess.run(["git", "commit", "-qam", "fake: valid agent again"], check=False)
    (node_dir / "HANDOFF.md").write_text(f"# Handoff {node_id}: fake\n## Hypothesis\nfake\n## What I did\nfake\n## Result\nquick: 0\n")
    (node_dir / "proposals.json").write_text(json.dumps([{"title": "fake child", "hypothesis": "fake child hyp", "type": "idea",
                                                          "expected_gain": "none", "risk": "none"}]))
end()
