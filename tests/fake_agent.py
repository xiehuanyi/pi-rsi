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
    if prompt.startswith("You maintain a research wiki"):
        evidence = json.JSONDecoder().raw_decode(prompt.split("\nNEW EVIDENCE\n", 1)[1])[0]
        eid = evidence[-1]["id"]
        end({"claims": [{"id": "fake-observation", "title": "Fake measured result",
                        "kind": "observation", "status": "supported", "statement": "The fake run completed.",
                        "scope": "Only this scripted test and protocol", "supports": [eid], "opposes": [],
                        "alternatives": ["No causal mechanism was tested."], "next_test": "Repeat on another input."}],
             "agenda": {"motivation": "Verify durable experimental context.", "method": "Scripted test.",
                        "what_changed": "An evidence record is available.", "open_questions": ["Does recall work?"],
                        "next_experiments": ["Ablate memory and compare recall."]}})
    elif prompt.startswith("You structure a setup review"):
        text = prompt.split("REVIEW\n<<<\n", 1)[1].rsplit("\n>>>", 1)[0]
        line = next(l for l in text.splitlines() if l.startswith("Question:"))
        end({"risks": ["Fixture evaluator is deterministic."], "questions": [{
             "id": "review_cadence", "question": line[len("Question: "):], "options": ["5", "3"], "recommended": "5",
             "rationale": "Scripted fixture.", "importance": "routine", "category": "review_frequency", "quote": line}]})
    elif prompt.startswith("You structure the human-proxy's answers"):
        text = prompt.split("ANSWERS TEXT\n<<<\n", 1)[1].rsplit("\n>>>", 1)[0]
        answers = [{"id": m.group(1), "answer": m.group(2), "quote": m.group(0)}
                   for m in re.finditer(r"\[(\w+)\] answer: (\S+)", text)]
        end({"answers": answers})
    elif prompt.startswith("You structure a course correction"):
        text = prompt.split("COURSE\n<<<\n", 1)[1].rsplit("\n>>>", 1)[0]
        line = next(l for l in text.splitlines() if l.startswith("Next direction:"))
        end({"diagnosis": "Scripted stall.", "direction": line, "direction_quote": line,
             "paused": ["repeating the fixture approach"], "setup_change": {"needed": False}})
    elif prompt.startswith("You structure a research lead's written decision"):
        text = prompt.split("DECISION TEXT\n<<<\n", 1)[1].rsplit("\n>>>", 1)[0]
        line = next(l for l in text.splitlines() if "build on" in l)
        end({"action": "continue", "action_quote": line, "parent": re.search(r"build on (\w+)", line).group(1),
             "title": "fake researched approach", "hypothesis": "test the fake approach", "type": "idea",
             "research_question": "Does the scripted loop recover?", "prediction": "A valid implementation evaluates.",
             "falsifier": "Evaluation fails.", "evidence": [], "budget": {"seconds": None, "max_trials": None},
             "alternatives": [{"title": "fake alternative", "parent": None, "why_not": "scripted"}],
             "reason": "The fixture task still has remaining work."})
    elif prompt.startswith("You structure a research lead's written result analysis"):
        handoff = prompt.split("HANDOFF\n<<<\n", 1)[1].rsplit("\n>>>", 1)[0]
        result = handoff.split("## Result\n", 1)[1].splitlines()[0]
        end({"observations": [result], "interpretation": "Fixture validates control flow, not research quality.",
             "noise_assessment": "No independent replication.", "belief_revisions": [],
             "competing_explanations": ["Deterministic fixture behavior."], "limitations": ["Not an LLM test."],
             "result_quote": result})
    elif "planner" in prompt.lower():
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

if mode == "resume" and prompt.startswith("Your submitted job"):  # woken after `rsi job submit`: finish the node
    nd = Path(re.search(r"`([^`]+)/PROGRESS.md`", prompt).group(1))
    result = (nd / "job_result.txt").read_text().strip() if (nd / "job_result.txt").exists() else "missing"
    with open(nd / "PROGRESS.md", "a") as f:
        f.write(f"- resumed after the submitted job; result {result}\n")
    Path("agent.py").write_text(Path("agent.py").read_text() + f"\n# job result {result}\n")
    subprocess.run(["git", "commit", "-qam", "fake: after the submitted job"], check=False)
    if "IMPLEMENTATION.md" in prompt:
        (nd / "IMPLEMENTATION.md").write_text(f"# Implementation {nd.name}: fake\n## What I built\nused job result {result}\n"
                                           "## How to run\nfake\n## Development results\nquick: 0\n")
        (nd / "DELIVERY.json").write_text(json.dumps({"component": "on", "reason": "fake"}))
    else:
        (nd / "HANDOFF.md").write_text(f"# Handoff {nd.name}: fake\n## Hypothesis\nfake\n## What I did\nused job\n## Result\nquick: 0\n")
        (nd / "proposals.json").write_text(json.dumps([{"title": "fake child", "hypothesis": "fake child hyp", "type": "idea",
                                                        "expected_gain": "none", "risk": "none"}]))
    end()
    sys.exit(0)

if mode == "resume":  # analysis session (job mode) or handoff rescue: append the official result to the handoff
    m = re.search(r"official score \([^)]*\): ([^\n]+)", prompt)
    nd = re.search(r"`([^`]+)/HANDOFF.md`", prompt)
    if nd:
        with open(Path(nd.group(1)) / "HANDOFF.md", "a") as f:
            f.write(f"\n(official result seen by fake analysis: {m.group(1) if m else '?'})\n")
    end()
    sys.exit(0)

if prompt.startswith("You are the setup reviewer of pi-rsi"):
    Path('REVIEW.md').write_text("# Setup review\nRisk: the fixture evaluator is deterministic.\n"
                                 "Question: How many experiments between full reviews? Options 5 or 3; I recommend 5.\n")
    end()
    sys.exit(0)
if prompt.startswith("You are the human-proxy of pi-rsi"):
    ids = re.findall(r"^\[(\w+)\] ", prompt, re.M)
    recommended = re.findall(r"^Reviewer recommends: (\S+?)\. ", prompt, re.M)
    Path('PROXY.md').write_text("".join(f"[{i}] answer: {r} because the human notes do not say otherwise.\n"
                                        for i, r in zip(ids, recommended)))
    end()
    sys.exit(0)
if prompt.startswith("You are a fresh reviewer of pi-rsi"):
    Path('COURSE.md').write_text("# Course correction\nDiagnosis: every fixture result is identical.\n"
                                 "Pause: repeating the fixture approach, because it never moves the score.\n"
                                 "Next direction: change one fixture input to test whether the score can move at all.\n")
    end()
    sys.exit(0)
if prompt.startswith("You are the research lead in pi-rsi"):
    # The prompt carries a bounded digest; like a real agent, read the complete snapshot file.
    snapshot = json.loads(Path(re.search(r"Complete snapshot \(.*?\): (\S+)", prompt).group(1)).read_text())
    parent = snapshot['parents'][-1]['id']
    decision = (f"Decision: continue.\nNext: build on {parent} and test one more fake approach.\n"
                "Alternative considered: a second fake approach; same information value. No reference search.\n")
    if "This is a REVIEW" in prompt.splitlines()[0]:
        Path('DECISION.md').write_text(decision)
    else:
        metrics = json.loads(Path(re.search(r"Official metrics \(excerpt; full file (.+?)\): ", prompt).group(1)).read_text())
        Path('HANDOFF.md').write_text('# Handoff\n## Result\nOfficial fixture score '+str(metrics['score'])+
            '\n## Noise assessment\nNo independent replication.\n## Belief revisions\nNone.\n'
            '## Competing explanations\nDeterministic fixture behavior.\n## Limitations\nNot an LLM test.\n')
        Path('NEXT.md').write_text(decision)
    end()
    sys.exit(0)

node_dir = Path(re.search(r"Node notes directory.*?`([^`]+)`", prompt).group(1))
node_id = re.search(r"- Node: `([^`]+)`", prompt).group(1)
retry = "this is a retry" in prompt.lower()
node_dir.mkdir(parents=True, exist_ok=True)
if os.environ.get("FAKE_SUBMIT_JOB") and not (node_dir / "jobs").exists():
    # A long command goes to the queue through the harness CLI; the session ends and is resumed later.
    rsi = os.environ.get("FAKE_RSI_BIN") or str(Path(__file__).resolve().parents[1] / "rsi")
    out = subprocess.run([rsi, "job", "submit", "--node-dir", str(node_dir), "--timeout", "120", "--", "bash", "-c",
                          f"sleep {os.environ['FAKE_SUBMIT_JOB']} && echo 42 > {node_dir}/job_result.txt"],
                         capture_output=True, text=True, check=True)
    with open(node_dir / "PROGRESS.md", "a") as f:
        f.write(f"# Progress {node_id}\n- submitted job {out.stdout.strip()}; ending the session until it finishes\n")
    end()
    sys.exit(0)
if Path("config.toml").exists() and Path("src/trainer.py").exists():   # toy long-job task: tweak the config, always succeed
    import hashlib
    h = int(hashlib.md5(node_id.encode()).hexdigest(), 16)
    lr = [0.005, 0.01, 0.02, 0.03, 0.001][h % 5]
    hidden = [16, 32, 64][h % 3]
    Path("config.toml").write_text(f"hidden = {hidden}\nlr = {lr}\nbatch = 64\nseed = 0\n")
    subprocess.run(["git", "commit", "-qam", f"fake: lr={lr} hidden={hidden}"], check=False)
    (node_dir / "PROGRESS.md").write_text(f"# Progress {node_id}\n- set lr={lr} hidden={hidden}\n")
    (node_dir / "HANDOFF.md").write_text(f"# Handoff {node_id}: fake\n## Hypothesis\nlr={lr} hidden={hidden}\n## What I did\nedited config\n## Result\nsmoke: not run\n")
    (node_dir / "proposals.json").write_text(json.dumps([{"title": "fake child", "hypothesis": "another config", "type": "idea",
                                                          "expected_gain": "none", "risk": "none"}]))
    end()
    sys.exit(0)
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
    if "IMPLEMENTATION.md schema" in prompt:
        (node_dir / "IMPLEMENTATION.md").write_text(f"# Implementation {node_id}: fake\n## What I built\nfake\n"
                                                    "## How to run\nfake\n## Development results\nquick: 0\n")
    else:
        (node_dir / "HANDOFF.md").write_text(f"# Handoff {node_id}: fake\n## Hypothesis\nfake\n## What I did\nfake\n## Result\nquick: 0\n")
        (node_dir / "proposals.json").write_text(json.dumps([{"title": "fake child", "hypothesis": "fake child hyp", "type": "idea",
                                                              "expected_gain": "none", "risk": "none"}]))
end()
