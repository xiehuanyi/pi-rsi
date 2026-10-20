"""Waiting without a thread: a queued official evaluation or a worker-submitted job frees the controller,
which keeps dispatching other branches and wakes the node when its task ends; a restart re-attaches."""
from __future__ import annotations

import json
import os
import signal
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from pi_rsi.config import SetupCfg, write_experiment_toml
from pi_rsi.orchestrator import Orchestrator
from tests.test_research_loop import make_cfg


def slow_cfg(root, sleep_s, max_nodes=3):
    """The research-loop fixture with an evaluator that takes `sleep_s` seconds. The sleep is written before
    any measurement, so the evaluation protocol is the same for the baseline and every node."""
    cfg = make_cfg(root)
    eval_py = Path(cfg.task.dir) / "eval" / "eval.py"
    eval_py.write_text(eval_py.read_text().replace("import argparse,json,runpy\n",
                                                   f"import argparse,json,runpy,time\ntime.sleep({sleep_s})\n"))
    cfg.search.patience = 10
    cfg.search.max_nodes = max_nodes
    cfg.search.max_waiting = 1
    cfg.setup = SetupCfg(enabled=False, course_k=99)
    return cfg


def events(cfg):
    return [json.loads(line) for line in cfg.events_path.read_text().splitlines()]


def stop_daemon(root):
    daemon = root / "jobs" / "jobd.json"
    if daemon.exists():
        try:
            os.killpg(json.loads(daemon.read_text())["pid"], signal.SIGTERM)
        except (ProcessLookupError, KeyError, ValueError, OSError):
            pass


class WaitingEvaluationTests(unittest.TestCase):
    def env(self, root, **extra):
        return patch.dict(os.environ, {"RSI_JOBS_DIR": str(root / "jobs"), "RSI_GPUS": "", **extra})

    def test_next_branch_is_implemented_while_a_result_is_pending(self):
        with tempfile.TemporaryDirectory() as d, self.env(Path(d)):
            root = Path(d)
            cfg = slow_cfg(root, 5)
            orch = Orchestrator(cfg, verbose=False)
            try:
                self.assertEqual(orch.run(), "max_nodes")
                done = [n for n in orch.tree.non_root() if n.status == "done"]
                self.assertEqual(len(done), 3, [(n.id, n.status, n.failure) for n in orch.tree.non_root()])
                self.assertTrue(all(n.worker.get("analysis") for n in done))
                evs = events(cfg)
                names = [e["event"] for e in evs]
                self.assertIn("eval_submitted", names)
                self.assertIn("task_wake", names)
                # The first node waited for its evaluation while the second was already being implemented.
                first_finish = next(i for i, e in enumerate(evs) if e["event"] in ("node_done", "node_failed"))
                started_before = {e["node"] for e in evs[:first_finish] if e["event"] == "node_start"}
                self.assertGreaterEqual(len(started_before), 2, started_before)
                # Never more results pending than allowed, and every wake consumed exactly one task.
                self.assertLessEqual(max((e.get("waiting") or 0) for e in evs if e["event"] == "stop_condition"), 1)
                for n in done:
                    record = json.loads(next((cfg.nodes_dir / n.id / "eval").glob("*.monitor.json")).read_text())
                    self.assertEqual((record["state"], record["wake_count"]), ("consumed", 1))
                    self.assertLessEqual(record["finished_at"], record["model_woken_at"])
                    self.assertIn("Harness measurement record", (cfg.nodes_dir / n.id / "HANDOFF.md").read_text())
                review = next(e for e in evs if e["event"] == "research_review" and e["cycle"] != "c000001")
                prompt = (cfg.dir / "cycles" / review["cycle"] / "research.prompt.md").read_text()
                self.assertIn("PENDING RESULTS", prompt)
                self.assertFalse([e for e in evs if e["event"] in ("research_failed", "memory_failed", "node_crash")])
            finally:
                orch.stop_flag.set()
                stop_daemon(root)

    def test_an_interrupted_controller_reattaches_to_the_pending_task_on_restart(self):
        with tempfile.TemporaryDirectory() as d, self.env(Path(d)):
            root = Path(d)
            cfg = slow_cfg(root, 6, max_nodes=2)
            orch = Orchestrator(cfg, verbose=False)
            try:
                thread = threading.Thread(target=orch.run)
                thread.start()
                deadline = time.time() + 120
                while time.time() < deadline and not orch.tree.by_status("waiting"):
                    time.sleep(0.2)
                waiting = [n.id for n in orch.tree.by_status("waiting")]
                self.assertTrue(waiting, "no node reached the waiting state")
                orch.stop_flag.set()
                thread.join(timeout=180)
                self.assertFalse(thread.is_alive())
                journal = json.loads((cfg.dir / "executions" / f"{waiting[0]}.json").read_text())
                self.assertEqual(journal["execution"]["state"], "waiting")
                final = json.loads((cfg.dir / "final.json").read_text())
                self.assertIn("unfinished_nodes", final["faults"])
                jobs_before = len(list((root / "jobs" / "queue").glob("*.json")))
                restarted = Orchestrator(cfg, verbose=False)
                self.assertEqual(restarted.run(), "max_nodes")
                done = [n for n in restarted.tree.non_root() if n.status == "done"]
                self.assertEqual(len(done), 2, [(n.id, n.status, n.failure) for n in restarted.tree.non_root()])
                evs = events(cfg)
                resumed = [e for e in evs if e["event"] == "monitor_resume" and e["node"] == waiting[0]]
                self.assertTrue(resumed)
                queue = {p.stem: json.loads(p.read_text()) for p in (root / "jobs" / "queue").glob("*.json")}
                owner = f"{cfg.name}/{waiting[0]}"
                self.assertGreaterEqual(len(queue), jobs_before)
                self.assertFalse([e for e in evs if e["event"] in ("research_failed", "node_crash")])
                self.assertTrue(all(j["status"] in ("done", "failed") for j in queue.values() if j["owner"] == owner))
            finally:
                orch.stop_flag.set()
                stop_daemon(root)


class WorkerJobTests(unittest.TestCase):
    def test_worker_submits_a_long_command_and_is_resumed_when_it_ends(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"RSI_JOBS_DIR": str(Path(d) / "jobs"),
                                                                           "RSI_GPUS": "", "FAKE_SUBMIT_JOB": "3"}):
            root = Path(d)
            cfg = make_cfg(root)
            cfg.search.max_nodes = 1
            cfg.search.patience = 10
            cfg.setup = SetupCfg(enabled=False, course_k=99)
            write_experiment_toml(cfg)  # `rsi job submit` reads the experiment's name from rsi.toml
            orch = Orchestrator(cfg, verbose=False)
            try:
                self.assertEqual(orch.run(), "max_nodes")
                node = orch.tree.non_root()[0]
                self.assertEqual(node.status, "done", node.failure)
                names = [e["event"] for e in events(cfg)]
                for name in ("worker_job_wait", "task_wake", "worker_resume", "eval_submitted"):
                    self.assertIn(name, names)
                self.assertLess(names.index("worker_job_wait"), names.index("worker_resume"))
                records = list((cfg.nodes_dir / node.id / "jobs").glob("*.json"))
                self.assertEqual(len(records), 1)
                job_id = json.loads(records[0].read_text())["job"]
                job = json.loads((root / "jobs" / "queue" / f"{job_id}.json").read_text())
                self.assertEqual((job["status"], job["owner"]), ("done", f"{cfg.name}/{node.id}/worker"))
                self.assertIn("job result 42", (cfg.worktrees_dir / node.id / "agent.py").read_text())
                self.assertIn("used job result 42", (cfg.nodes_dir / node.id / "IMPLEMENTATION.md").read_text())
                self.assertEqual(node.worker["job_rounds"], 1)
                journal = json.loads((cfg.dir / "executions" / f"{node.id}.json").read_text())
                self.assertEqual(len(journal["attempts"]), 1)  # the resumed session belongs to the same attempt
                self.assertGreater(journal["attempts"][0]["worker_seconds"], 0)
                resume_log = next((cfg.nodes_dir / node.id / "attempts").glob("*/runner.resume1.prompt.md"))
                self.assertIn(job_id, resume_log.read_text())
            finally:
                orch.stop_flag.set()
                stop_daemon(root)


if __name__ == "__main__":
    unittest.main()
