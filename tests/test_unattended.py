"""Long unattended runs: bounded prompts, protocol-bound measurements, budget stops vs. pending faults,
queue-daemon recovery, evaluation resume and bounded wiki retries. Each test replays a failure mode
found in review; none needs a model, a GPU or the network."""
from __future__ import annotations

import datetime
import functools
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pi_rsi import gitops, jobs
from pi_rsi.config import ExperimentCfg, TaskCfg
from pi_rsi.evaluator import EvalError, run_eval
from pi_rsi.measurement import ProtocolMismatch, evaluation_protocol, validated_measurement
from pi_rsi.monitor import TaskMonitor, evaluation_identity
from pi_rsi.orchestrator import Orchestrator
from pi_rsi.runner import make_runner
from pi_rsi.runner.base import Runner
from pi_rsi.tree import Node
from pi_rsi.util import atomic_write_json, read_json
from pi_rsi.worker import run_node
from tests import test_memory, test_stage_recovery
from tests.test_research_loop import decision, make_cfg

FAKE_PI = """#!/usr/bin/env python3
import json, sys
prompt = sys.stdin.read()
print(json.dumps({"type": "session", "id": "s1"}))
print(json.dumps({"type": "message_end", "message": {"role": "assistant", "stopReason": "stop",
      "content": [{"type": "text", "text": f"received {len(prompt)} chars, {len(sys.argv)} argv"}]}}))
"""


def iso_ago(seconds):
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=seconds)).replace(
        microsecond=0).isoformat()


class PromptTransportTests(unittest.TestCase):
    def test_pi_prompt_goes_through_stdin_not_one_argv_string(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "pi").write_text(FAKE_PI)
            (d / "pi").chmod(0o755)
            with patch.dict(os.environ, {"RSI_PI_BIN": str(d / "pi")}):
                runner = make_runner("pi", "mock/model", "")
            res = runner.run_agent("x" * 300_000, cwd=d, log_path=d / "logs" / "run.jsonl", max_turns=1,
                                   timeout_s=60, idle_timeout_s=60)  # > 128 KiB: one argv string would be E2BIG
            self.assertTrue(res.ok, res.error)
            self.assertIn("received 300000 chars", res.final_text)
            start = json.loads((d / "logs" / "run.jsonl").read_text().splitlines()[0])
            self.assertLess(len(json.dumps(start["cmd"])), 2000)
            _, res = runner.ask_json("y" * 200_000, cwd=d, log_path=d / "logs" / "json.jsonl",
                                     schema={"type": "object"}, timeout_s=60)
            self.assertIn("received 2000", res.final_text)
            self.assertIn("JSON schema", (d / "logs" / "json.prompt.md").read_text())  # exact stdin record

    def test_unstartable_command_is_a_failed_run_not_a_crash(self):
        class HugeArgv(Runner):
            def build_agent_cmd(self, prompt_file, cwd, max_turns, session_dir, session_id=None):
                return ["/bin/true", prompt_file.read_text()]

        with tempfile.TemporaryDirectory() as d:
            res = HugeArgv("m").run_agent("z" * 300_000, cwd=Path(d), log_path=Path(d) / "r.jsonl",
                                          max_turns=1, timeout_s=10, idle_timeout_s=10)
        self.assertFalse(res.ok)
        self.assertIn("could not start", res.error)


class BoundedThinkTests(unittest.TestCase):
    def test_review_prompt_stays_bounded_and_every_parent_stays_selectable(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = make_cfg(Path(d))
            cfg.memory.enabled = False
            orch = Orchestrator(cfg, verbose=False)
            orch.memory.enabled = False
            orch.tree.nodes["root"] = Node("root", None, 0, "baseline", "", status="done", score=0.0, commit="c0")
            for i in range(1, 601):
                orch.tree.nodes[f"n{i:03d}"] = Node(
                    f"n{i:03d}", "root", 1, f"approach {i} " + "t" * 200, "h" * 3000, status="done",
                    score=i / 1000, commit=f"c{i}", summary="s" * 2000, finished_order=i)
            orch.tree._counter = 600
            orch.tree.save()
            snapshot = orch.research._snapshot(orch.scheduler)
            self.assertEqual(len(snapshot["parents"]), 601)
            self.assertGreater(len(json.dumps(snapshot)), 1_000_000)
            cycle = orch.research._new_cycle()
            atomic_write_json(cycle / "snapshot.json", snapshot)
            prompt = orch.research._review_prompt(snapshot, cycle, "fixture review")
            self.assertLess(len(prompt), cfg.research.context_chars + 20_000)
            self.assertIn(str(cycle / "snapshot.json"), prompt)
            self.assertIn("more in the snapshot file", prompt)
            shown = {json.loads(line)["id"] for line in prompt.splitlines() if line.startswith('{"id"')}
            self.assertIn("n600", shown)  # the best branch is always in the digest
            hidden = next(p["id"] for p in snapshot["parents"] if p["id"] not in shown)
            # Validation uses the complete snapshot: a parent outside the digest is still eligible.
            out = orch.research._validate(decision(hidden), snapshot, cycle)
            self.assertEqual(out["candidates"][0]["parent"], hidden)


class ProtocolBindingTests(unittest.TestCase):
    setUp = test_stage_recovery.StageRecoveryTests.setUp
    tearDown = test_stage_recovery.StageRecoveryTests.tearDown
    assert_scientific_artifacts_unchanged = test_stage_recovery.StageRecoveryTests.assert_scientific_artifacts_unchanged

    def bind(self):
        root = self.orch.tree.get("root")
        atomic_write_json(self.cfg.nodes_dir / "root" / "eval" / f"metrics.{self.cfg.task.official_seedset}.json",
                          {"score": root.score})
        self.orch.executions.migrate(self.orch.tree)
        self.orch.check_protocol()
        self.evaluator = Path(self.cfg.task.dir) / "eval" / "eval.py"
        self.original = self.evaluator.read_text()

    def test_scores_from_another_evaluator_are_quarantined_not_mixed(self):
        self.bind()
        before = evaluation_protocol(self.cfg)
        self.assertEqual(self.orch.tree.get("root").measurement["protocol"], before)
        self.assertEqual(self.orch.tree.best().id, "n001")
        self.evaluator.write_text(self.original + "\n# scoring fix\n")
        self.assertNotEqual(evaluation_protocol(self.cfg), before)
        with self.assertRaises(ProtocolMismatch):
            validated_measurement(self.orch, self.node)
        self.orch.check_protocol()
        self.assertEqual(self.node.measurement["state"], "stale")
        self.assertIsNone(self.orch.tree.best())  # no old score is selection evidence any more
        self.assertFalse(self.orch.scheduler.expandable(self.orch.tree.get("root")))
        self.assertEqual(self.orch.scheduler.stop_reason(), "protocol_changed")
        self.assertIn("protocol_changed", self.orch.scheduler.pending_faults())
        self.cfg.task.final_seedset, self.cfg.task.final_eval_root = "full", True
        with patch("pi_rsi.orchestrator.run_eval", side_effect=AssertionError("confirmation must wait")):
            self.orch.finish("protocol_changed")
        final = json.loads((self.cfg.dir / "final.json").read_text())
        self.assertIn("protocol_changed", final["faults"])
        self.assertNotIn("best_final_score", final)
        # Restoring the evaluator restores the records; nothing was invalidated or rerun.
        self.evaluator.write_text(self.original)
        self.orch.check_protocol()
        self.assertTrue(self.node.measurement_valid)
        self.assertNotIn("protocol_change", self.orch.tree.meta)
        self.assertNotEqual(self.orch.scheduler.stop_reason(), "protocol_changed")
        validated_measurement(self.orch, self.node)
        self.assert_scientific_artifacts_unchanged()

    def test_stale_measurement_is_neither_invalidated_nor_rerun(self):
        self.bind()
        self.evaluator.write_text(self.original + "\n# changed\n")
        self.orch.check_protocol()
        self.assertEqual(self.node.status, "incomplete")  # was mid-analysis: parked, not resumed
        self.orch.recover()
        self.assertEqual(self.orch.executions.read(self.node)["measurement"]["state"], "stale")
        self.orch.tree.update(self.node, status="planned")
        with patch("pi_rsi.worker.run_eval", side_effect=AssertionError("no evaluation replay")):
            run_node(self.orch, self.node)
        self.assertEqual(self.orch.executions.read(self.node)["measurement"]["state"], "stale")
        self.assertNotEqual(self.node.measurement.get("state"), "invalid")
        self.assert_scientific_artifacts_unchanged()

    def test_reeval_rebinds_under_the_new_protocol_and_keeps_history(self):
        self.bind()
        self.evaluator.write_text(self.original + "\n# changed\n")
        self.orch.check_protocol()

        def remeasure(cfg, worktree, seedset, out_dir, **kwargs):
            metrics = {"score": 1.2 if worktree != cfg.repo_dir else 1.0}
            atomic_write_json(out_dir / f"metrics.{seedset}.json", metrics)
            return metrics

        from pi_rsi.cli import _reevaluate
        with patch("pi_rsi.evaluator.run_eval", side_effect=remeasure):
            _reevaluate(self.orch)
        current = evaluation_protocol(self.cfg)
        self.assertNotIn("protocol_change", self.orch.tree.meta)
        for node_id in ("root", "n001"):
            record = self.orch.executions.read(self.orch.tree.get(node_id))
            self.assertEqual(record["measurement"]["protocol"], current)
            self.assertEqual(record["measurement_history"][-1]["state"], "stale")

    def test_pre_binding_records_are_adopted_once(self):
        legacy = {k: v for k, v in self.node.worker["evaluation_validated"].items() if k != "protocol"}
        self.node.worker["evaluation_validated"] = legacy
        self.orch.tree.save()
        self.bind()
        self.assertEqual(self.orch.executions.read(self.node)["measurement"]["protocol"], evaluation_protocol(self.cfg))
        self.evaluator.write_text(self.original + "\n# changed\n")
        self.orch.check_protocol()
        self.assertEqual(self.node.measurement["state"], "stale")


class StopVersusFaultTests(unittest.TestCase):
    setUp = test_stage_recovery.StageRecoveryTests.setUp
    tearDown = test_stage_recovery.StageRecoveryTests.tearDown

    def finish(self, reason):
        self.cfg.task.final_seedset, self.cfg.task.final_eval_root = "full", True
        final_eval = Mock(return_value={"score": 1.3})
        with patch("pi_rsi.orchestrator.run_eval", final_eval):
            self.orch.finish(reason)
        return json.loads((self.cfg.dir / "final.json").read_text()), final_eval

    def test_wallclock_stop_cannot_hide_an_incomplete_handoff(self):
        self.cfg.search.max_wallclock_s = 60
        self.orch.started_ts -= 120
        self.orch.tree.update(self.node, status="incomplete")
        self.assertEqual(self.orch.scheduler.stop_reason(), "wallclock")
        final, final_eval = self.finish("wallclock")
        self.assertEqual(final["stop_reason"], "wallclock")
        self.assertEqual(final["faults"], ["postprocess_failed"])
        self.assertNotIn("best_final_score", final)
        final_eval.assert_not_called()

    def test_wallclock_stop_cannot_hide_a_failed_think(self):
        self.cfg.search.max_wallclock_s = 60
        self.orch.started_ts -= 120
        self.orch.tree.update(self.node, status="done")
        self.orch.tree.meta["research_error"] = {"cycle": "c000001", "error": "agent crashed"}
        final, final_eval = self.finish(self.orch.scheduler.stop_reason())
        self.assertEqual(final["faults"], ["research_failed"])
        final_eval.assert_not_called()

    def test_clean_budget_stop_still_confirms(self):
        self.cfg.search.max_wallclock_s = 60
        self.orch.started_ts -= 120
        self.orch.tree.update(self.node, status="done")
        final, final_eval = self.finish(self.orch.scheduler.stop_reason())
        self.assertEqual(final["faults"], [])
        self.assertEqual(final["best_final_score"], 1.3)
        self.assertTrue(final_eval.called)


class ThinkAdmissionTests(unittest.TestCase):
    def test_exhausted_budget_before_think_is_a_stop_not_a_research_failure(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = make_cfg(Path(d))
            orch = Orchestrator(cfg, verbose=False)
            orch.tree.add(Node("root", None, 0, "baseline", "", status="done", score=10, commit="root-code"))
            cfg.search.max_wallclock_s = 60
            orch.started_ts -= 61
            orch.research.runner = Mock(run_agent=Mock(side_effect=AssertionError("no THINK after the budget")))
            self.assertIsNone(orch.scheduler.next_node())
            self.assertNotIn("research_error", orch.tree.meta)
            self.assertFalse((cfg.dir / "cycles").exists() and list((cfg.dir / "cycles").iterdir()))
            self.assertEqual(orch.scheduler.stop_reason(), "wallclock")
            self.assertEqual(orch.scheduler.pending_faults(), [])


class QueueDaemonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {"RSI_JOBS_DIR": str(self.dir / "q"), "RSI_GPUS": ""})
        self.env.start()
        self.procs = []

    def tearDown(self):
        record = read_json(self.dir / "q" / "jobd.json")
        if record and record["pid"] != os.getpid():  # in-process ticks write our own pid
            try:
                os.kill(record["pid"], signal.SIGTERM)
            except ProcessLookupError:
                pass
        for proc in self.procs:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
        self.env.stop()
        self.tmp.cleanup()

    def orphan(self, started_ago, **kw):
        """A job its (dead) daemon left `running` while the process itself kept going."""
        proc = subprocess.Popen(["sleep", "120"], cwd=self.dir, start_new_session=True)
        self.procs.append(proc)
        job = jobs.Job(id=f"orphan{len(self.procs)}", cmd=["sleep", "120"], cwd=str(self.dir), status="running",
                       pid=proc.pid, started_at=iso_ago(started_ago), proc_identity=jobs._proc_identity(proc.pid), **kw)
        job.save()
        return job, proc

    def test_adopted_job_keeps_its_timeout(self):
        job, proc = self.orphan(3600, timeout_s=60)
        running = jobs._adopt_orphans([], [])
        self.assertIn(job.id, running)
        jobs._daemon_tick(jobs.jobs_dir(), [], [], running, 2)
        saved = jobs.Job.load(job.id)
        self.assertEqual(saved.status, "killed")
        self.assertTrue(saved.reason.startswith("timeout"), saved.reason)
        self.assertIsNotNone(saved.duration_s)
        self.assertEqual(proc.wait(timeout=20), -signal.SIGTERM)
        self.assertEqual(running, {})

    def test_adopted_job_keeps_stall_detection_and_healthy_jobs_keep_running(self):
        metrics = self.dir / "metrics.jsonl"
        metrics.write_text('{"step": 1, "value": 0.5}\n')
        os.utime(metrics, (time.time() - 3600, time.time() - 3600))
        stalled, _ = self.orphan(3600, timeout_s=86400, stall_s=600, metrics_path=str(metrics))
        healthy, healthy_proc = self.orphan(5, timeout_s=86400, stall_s=600)
        running = jobs._adopt_orphans([], [])
        jobs._daemon_tick(jobs.jobs_dir(), [], [], running, 2)
        self.assertTrue(jobs.Job.load(stalled.id).reason.startswith("stalled"))
        self.assertEqual(jobs.Job.load(healthy.id).status, "running")
        self.assertIsNone(healthy_proc.poll())
        self.assertEqual(jobs.Job.load(stalled.id).last_step, 1)

    def test_recycled_pid_is_never_adopted_or_signalled(self):
        bystander = subprocess.Popen(["sleep", "120"], start_new_session=True)
        self.procs.append(bystander)
        job = jobs.Job(id="recycled", cmd=["train"], cwd=str(self.dir), status="running", pid=bystander.pid,
                       started_at=iso_ago(10), proc_identity="another-boot:12345")
        job.save()
        jobs.cancel(job.id)
        self.assertEqual(jobs._adopt_orphans([], []), {})
        self.assertEqual(jobs.Job.load(job.id).status, "failed")
        time.sleep(0.2)
        self.assertIsNone(bystander.poll())

    def test_one_daemon_per_queue_and_one_launch_per_job(self):
        marker = self.dir / "launches.txt"
        job = jobs.submit([sys.executable, "-c", f"open({str(marker)!r}, 'a').write('x\\n')"], self.dir)
        threads = [threading.Thread(target=jobs.ensure_daemon, kwargs={"gpus": []}) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
        extra = subprocess.run([sys.executable, "-m", "pi_rsi.cli", "jobd", "--gpus", ""], env=env,
                               capture_output=True, text=True, timeout=60)
        self.assertIn("another daemon holds", extra.stdout)
        self.assertEqual(jobs.wait(job.id, poll_s=0.2).status, "done")
        self.assertEqual(marker.read_text(), "x\n")
        deadline = time.time() + 15
        while time.time() < deadline and len(self.daemons()) != 1:
            time.sleep(0.3)
        self.assertEqual(len(self.daemons()), 1)

    def daemons(self):
        found = []
        for proc in Path("/proc").iterdir():
            try:
                if (proc.name.isdigit() and b"jobd" in (proc / "cmdline").read_bytes()
                        and f"RSI_JOBS_DIR={self.dir / 'q'}".encode() in (proc / "environ").read_bytes().split(b"\0")):
                    found.append(int(proc.name))
            except OSError:
                continue
        return found

    def test_early_stop_counts_new_checkpoints_not_polls(self):
        incumbent, metrics = self.dir / "inc.jsonl", self.dir / "m.jsonl"
        incumbent.write_text("".join(json.dumps({"step": s, "value": 1.0}) + "\n" for s in range(1, 21)))
        job = jobs.Job(id="es", cmd=["true"], cwd=str(self.dir), metrics_path=str(metrics),
                       incumbent_path=str(incumbent),
                       early_stop={"warmup_frac": 0.3, "margin": 0.1, "patience_points": 3, "higher_is_better": True})
        r = jobs._Running(job, SimpleNamespace(pid=0, poll=lambda: None))
        metrics.write_text(json.dumps({"step": 10, "value": 0.1}) + "\n")
        for _ in range(10):  # one bad checkpoint seen by ten polls: training did not advance
            jobs._update_progress(job, r)
            self.assertEqual(jobs._should_kill(job, r), "")
        with metrics.open("a") as f:
            f.write(json.dumps({"step": 11, "value": 0.1}) + "\n")
        jobs._update_progress(job, r)
        self.assertEqual(jobs._should_kill(job, r), "")
        with metrics.open("a") as f:
            f.write(json.dumps({"step": 12, "value": 0.1}) + "\n")
        jobs._update_progress(job, r)
        self.assertTrue(jobs._should_kill(job, r).startswith("early stop: 3 checkpoints"))


class EvaluationResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {"RSI_JOBS_DIR": str(root / "q")})
        self.env.start()
        self.patches = [patch("pi_rsi.jobs.ensure_daemon"),
                        patch("pi_rsi.jobs.wait", functools.partial(jobs.wait, poll_s=0.1))]
        for p in self.patches:
            p.start()
        (root / "task" / "eval").mkdir(parents=True)
        (root / "task" / "eval" / "run.py").write_text("# frozen evaluator\n")
        self.cfg = ExperimentCfg("resume", root / "exp", TaskCfg(
            name="resume", dir=str(root / "task"), official_seedset="proxy", job_enabled=True, job_resumable=True,
            job_budgets={"proxy": 1}, job_command="python3 train.py --budget {budget} --run-dir {run_dir} {resume_flag}"))
        self.wt = root / "wt"
        self.wt.mkdir()
        (self.wt / "train.py").write_text("print('train')\n")
        gitops.init_repo(self.wt)
        self.out = root / "exp" / "nodes" / "n001" / "eval"
        self.run_dir = self.out / "run.proxy"
        self.monitor = TaskMonitor(self.out / "metrics.proxy.monitor.json")

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.env.stop()
        self.tmp.cleanup()

    def command(self, resume):
        from pi_rsi.evaluator import job_command
        return job_command(self.cfg, "proxy", self.run_dir, resume=resume)

    def job(self, resume, status):
        job = jobs.submit(self.command(resume), self.wt, result_path=str(self.run_dir / "metrics.json"))
        job.status = status
        job.save()
        return job

    def complete_next(self, job_id=None, score=0.5):
        """Play the daemon: finish the given job, or the next job that gets queued."""
        def finish():
            deadline = time.time() + 20
            while time.time() < deadline:
                todo = [j for j in jobs.list_jobs() if (j.id == job_id if job_id else j.status == "queued")]
                if todo:
                    atomic_write_json(self.run_dir / "metrics.json", {"score": score})
                    todo[0].status, todo[0].exit_code = "done", 0
                    todo[0].save()
                    return
                time.sleep(0.05)
        thread = threading.Thread(target=finish)
        thread.start()
        return thread

    def evaluate(self):
        return run_eval(self.cfg, self.wt, "proxy", self.out, owner="resume/n001", resume=True)

    def test_restart_waits_on_the_running_resume_attempt(self):
        # State left by a controller that died during attempt 1 (written with per-attempt identities).
        self.run_dir.mkdir(parents=True)
        self.job(False, "failed")
        live = self.job(True, "running")
        atomic_write_json(self.monitor.path, {"identity": TaskMonitor.fingerprint(
            evaluation_identity(self.cfg, self.wt, self.command(True))), "job": live.id, "state": "running"})
        thread = self.complete_next(live.id)
        metrics = self.evaluate()  # previously: "cannot replace a still-active monitored task"
        thread.join()
        self.assertEqual(metrics["score"], 0.5)
        self.assertEqual(metrics["_eval"]["job"], live.id)
        self.assertEqual(len(jobs.list_jobs()), 2)  # nothing resubmitted
        self.assertEqual(self.monitor.attempt(), 1)

    def test_restart_after_a_failed_first_attempt_resumes_instead_of_restarting(self):
        self.run_dir.mkdir(parents=True)
        failed = self.job(False, "failed")
        atomic_write_json(self.monitor.path, {"identity": TaskMonitor.fingerprint(
            evaluation_identity(self.cfg, self.wt, self.command(False))), "job": failed.id, "attempt": 0})
        thread = self.complete_next()
        metrics = self.evaluate()
        thread.join()
        resumed = jobs.Job.load(metrics["_eval"]["job"])
        self.assertIn("--resume", resumed.cmd)
        self.assertEqual(self.monitor.attempt(), 1)

    def test_attempt_budget_survives_restarts(self):
        self.run_dir.mkdir(parents=True)
        last = self.job(True, "failed")
        atomic_write_json(self.monitor.path, {"identity": TaskMonitor.fingerprint(
            evaluation_identity(self.cfg, self.wt, self.command(False))), "job": last.id, "attempt": 1})
        with self.assertRaises(EvalError):
            self.evaluate()
        self.assertEqual(len(jobs.list_jobs()), 1)  # no third attempt after a restart

    def test_a_new_evaluation_request_starts_from_the_first_attempt(self):
        self.run_dir.mkdir(parents=True)
        last = self.job(True, "failed")
        atomic_write_json(self.monitor.path, {"identity": TaskMonitor.fingerprint(
            evaluation_identity(self.cfg, self.wt, self.command(False))), "job": last.id, "attempt": 1})
        thread = self.complete_next()
        metrics = run_eval(self.cfg, self.wt, "proxy", self.out, owner="resume/n001")  # e.g. after a retry
        thread.join()
        self.assertNotIn("--resume", jobs.Job.load(metrics["_eval"]["job"]).cmd)


class WikiRetryTests(unittest.TestCase):
    setUp = test_memory.MemoryTests.setUp
    tearDown = test_memory.MemoryTests.tearDown
    node = test_memory.MemoryTests.node

    def expire(self, quarantine=False):
        """Let the persisted backoff (or a set-aside packet's retry time) elapse."""
        status = self.mem.reflection_status()
        status["retry_after"] = 0
        if quarantine:
            for item in status["quarantined"].values():
                item["retry_at"] = 0
        atomic_write_json(self.mem.root / "reflection_status.json", status)

    def test_failing_batch_is_retried_isolated_and_never_blocks_later_evidence(self):
        for i in range(1, 4):
            self.node(f"n00{i}", score=i)
        self.mem.sync(self.tree)
        poison = self.mem.pending()[0]["id"]
        batches, cured = [], [False]

        def compile_batch(utility, state, batch, review):
            batches.append([p["id"] for p in batch])
            if poison in batches[-1] and not cured[0]:
                raise RuntimeError("model call failed for this batch")
            data = {"claims": [test_memory.claim(batch[0]["id"], id=f"claim-{len(batches)}")],
                    "agenda": test_memory.agenda()}
            return self.mem._validate(data, state, batch, set())

        self.mem._compile = compile_batch
        with self.assertRaises(RuntimeError):
            self.mem.reflect(None, force=True)
        self.assertFalse(self.mem.reflect(None, force=True))  # backoff: no paid retry loop
        self.assertEqual(len(batches), 1)
        for _ in range(3):  # the batch shrinks after each failure until the poison packet is alone
            self.expire()
            with self.assertRaises(RuntimeError):
                self.mem.reflect(None, force=True)
        self.assertEqual([len(b) for b in batches], [3, 3, 2, 1])
        self.assertIn(poison, self.mem.reflection_status()["quarantined"])
        self.expire()
        while self.mem.reflect(None, force=True):  # evidence behind the failing packet compiles
            pass
        self.assertEqual([p["id"] for p in self.mem.pending()], [poison])
        self.assertIn(poison, self.mem.context("anything"))
        self.node("n004", score=4)
        self.mem.sync(self.tree)
        self.assertTrue(self.mem.reflect(None, force=True))  # new evidence compiles without delay
        self.expire(quarantine=True)
        with self.assertRaises(RuntimeError):  # the set-aside packet gets an isolated, slow retry
            self.mem.reflect(None, force=True)
        self.assertEqual(batches[-1], [poison])
        self.assertEqual(self.mem.reflection_status()["streak"], 0)  # and does not delay the queue
        cured[0] = True
        self.assertTrue(self.mem.reflect(None, force=True, retry_now=True))  # a human retry runs now
        self.assertEqual(self.mem.pending(), [])
        self.assertEqual(self.mem.reflection_status()["quarantined"], {})


if __name__ == "__main__":
    unittest.main()
