"""Stdlib tests for visualization payload rendering (no tree.html / tree.js edits)."""
from __future__ import annotations

import json
import math
import tempfile
import threading
import unittest
from pathlib import Path

from pi_rsi.config import ExperimentCfg, TaskCfg
from pi_rsi.render import build_data, layout, render_all, render_bundle, render_html
from pi_rsi.tree import Node, Tree


def _cfg(tmp: Path, **task_kw) -> ExperimentCfg:
    task = TaskCfg(name=task_kw.pop("name", "toy"), **task_kw)
    return ExperimentCfg(name="exp1", dir=tmp, task=task)


def _tree(tmp: Path, meta=None) -> Tree:
    t = Tree(tmp / "tree.json", meta=meta or {})
    t.add(Node("root", None, 0, "baseline", "", status="done", score=1.0,
               created_at="2026-01-01T00:00:00+00:00", started_at="2026-01-01T00:00:01+00:00"))
    return t


def _payload_json(html: str) -> dict:
    marker = "window.__RSI_DATA__ = "
    i = html.find(marker)
    if i < 0:
        raise AssertionError("inline payload missing")
    rest = html[i + len(marker):]
    end = rest.find(";</script>")
    if end < 0:
        end = rest.find(";\n")
    return json.loads(rest[:end])


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.cfg = _cfg(self.dir)
        self.tree = _tree(self.dir, meta={"created_at": "2026-01-01T00:00:00+00:00", "higher_is_better": True})

    def test_self_contained_and_external_renders(self):
        data = build_data(self.cfg, self.tree, {}, {"status": "running"})
        inline = render_html(data, external=False)
        self.assertIn("window.__RSI_DATA__", inline)
        self.assertNotIn('src="data.js"', inline)
        self.assertIn("<script>", inline)
        parsed = _payload_json(inline)
        self.assertEqual(parsed["experiment"], "exp1")
        self.assertEqual(parsed["task"], "toy")
        self.assertIn("nodes", parsed)
        self.assertEqual(parsed["best"], "root")

        external = render_html(data, external=True)
        self.assertIn('<script src="data.js"></script>', external)
        self.assertIn('<script src="tree.js"></script>', external)
        self.assertNotIn("window.__RSI_DATA__", external)

        out = self.dir / "bundle"
        render_bundle(self.cfg, self.tree, out, title="Bundle title", back_link="/rsi/notes/")
        index = (out / "index.html").read_text(encoding="utf-8")
        js = (out / "data.js").read_text(encoding="utf-8")
        self.assertTrue((out / "tree.js").exists())
        self.assertIn('src="data.js"', index)
        self.assertIn('src="tree.js"', index)
        self.assertNotIn("window.__RSI_DATA__", index)
        self.assertTrue(js.startswith("window.__RSI_DATA__ = "))
        bundled = json.loads(js[len("window.__RSI_DATA__ = "):].rstrip().rstrip(";"))
        self.assertEqual(bundled["official_seedset"], "validation")
        self.assertIn("/rsi/notes/", index)

        render_all(self.cfg, self.tree, {}, {"status": "done"})
        page = (self.dir / "tree.html").read_text(encoding="utf-8")
        self.assertIn("window.__RSI_DATA__", page)
        self.assertTrue((self.dir / "tree.md").exists())

    def test_title_and_back_link_escaping(self):
        data = build_data(self.cfg, self.tree, {}, {})
        evil_title = '</title><script>alert(1)</script>" onload="alert(1)'
        html_out = render_html(data, title=evil_title, back_link='javascript:alert(1)')
        self.assertNotIn("</title><script>", html_out)
        self.assertIn("&lt;/title&gt;", html_out)
        self.assertNotIn("javascript:", html_out.lower())
        self.assertNotIn("href=\"javascript", html_out.lower())

        data_scheme = render_html(data, back_link="DATA:text/html,<script>alert(1)</script>")
        self.assertNotIn("data:text/html", data_scheme.lower())
        self.assertNotIn("← RSI notes", data_scheme)
        self.assertNotIn("javascript:alert", render_html(data, back_link="javascript:alert(1)"))

        quoted = render_html(data, back_link='https://example.test/" onclick="alert(1)')
        self.assertIn("&quot;", quoted)
        self.assertNotIn('onclick="alert', quoted)
        self.assertIn("href=\"https://example.test/", quoted)

        ok = render_html(data, back_link="/rsi/experiments/exp1/")
        self.assertIn('href="/rsi/experiments/exp1/"', ok)

        default_title = render_html({**data, "experiment": "a<b>", "task": "c&d"})
        self.assertIn("&lt;", default_title)
        self.assertIn("&amp;", default_title)

    def test_nonfinite_payload_is_valid_json(self):
        n = Node("n001", "root", 1, "nan-node", "", status="done",
                 score=float("nan"), metrics={"loss": float("inf"), "acc": -float("inf"), "ok": 1.5})
        self.tree.add(n)
        data = build_data(self.cfg, self.tree, {"worker": {"cost_usd": float("nan")}}, {})
        data["reference_scores"] = {"x": float("inf")}
        html_out = render_html(data)
        self.assertNotIn("NaN", html_out)
        self.assertNotIn("Infinity", html_out)
        parsed = _payload_json(html_out)
        node = next(x for x in parsed["nodes"] if x["id"] == "n001")
        self.assertIsNone(node["score"])
        self.assertIsNone(node["metrics"]["loss"])
        self.assertIsNone(node["metrics"]["acc"])
        self.assertEqual(node["metrics"]["ok"], 1.5)
        self.assertIsNone(parsed["costs"]["worker"]["cost_usd"])
        self.assertIsNone(parsed["reference_scores"]["x"])
        json.loads(json.dumps(parsed, allow_nan=False))

    def test_orphan_layout_does_not_overlap(self):
        t = Tree(self.dir / "orphan.json")
        t.add(Node("root", None, 0, "root", "", status="done", score=0))
        t.add(Node("n001", "root", 1, "child", "", status="done", score=1))
        t.add(Node("orphan_a", None, 0, "oa", "", status="done", score=0))
        t.add(Node("orphan_b", None, 0, "ob", "", status="done", score=0))
        t.add(Node("island", "missing", 0, "island", "", status="done", score=0))
        t.add(Node("isle_l", "island", 1, "left", "", status="done", score=0))
        t.add(Node("isle_r", "island", 1, "right", "", status="done", score=0))
        pos = layout(t)
        xs = [pos[k][0] for k in ("orphan_a", "orphan_b", "isle_l", "isle_r")]
        self.assertEqual(len(xs), len(set(xs)))
        self.assertLess(pos["isle_l"][0], pos["isle_r"][0])
        self.assertEqual(pos["island"][0], (pos["isle_l"][0] + pos["isle_r"][0]) / 2)
        self.assertEqual(pos["root"][1], 0.0)
        self.assertEqual(pos["n001"][1], 1.0)
        self.assertEqual(pos["root"][0], pos["n001"][0])  # single child: parent centered on that leaf
        data = build_data(self.cfg, t, {}, {})
        by_id = {n["id"]: n for n in data["nodes"]}
        self.assertEqual(by_id["island"]["x"], pos["island"][0])
        self.assertNotEqual(by_id["orphan_a"]["x"], by_id["orphan_b"]["x"])

    def test_metadata_and_snapshot_consistency(self):
        self.cfg.task.official_seedset = "validation"
        self.cfg.task.final_seedset = "holdout"
        n = Node("n001", "root", 1, "better", "", status="done", score=3.0,
                 created_at="2026-02-01T00:00:00+00:00")
        self.tree.add(n)
        state = {"started_at": "2099-01-01T00:00:00+00:00", "status": "running"}
        data = build_data(self.cfg, self.tree, {}, state)
        self.assertEqual(data["official_seedset"], "validation")
        self.assertEqual(data["final_seedset"], "holdout")
        self.assertEqual(data["experiment_started_at"], "2026-01-01T00:00:00+00:00")
        self.assertNotEqual(data["experiment_started_at"], state["started_at"])
        self.assertEqual(data["best"], "n001")
        self.assertEqual(data["root_score"], 1.0)
        self.assertIn("generated_at", data)
        self.assertIn("search", data)
        self.assertEqual(len(data["nodes"]), 2)

        # meta.created_at missing -> earliest valid node created/started (not state.started_at)
        t2 = _tree(self.dir / "b")
        t2.nodes["root"].created_at = "2026-03-02T00:00:00+00:00"
        t2.nodes["root"].started_at = "2026-03-01T00:00:00+00:00"
        t2.add(Node("n001", "root", 1, "x", "", status="done", score=2.0,
                    created_at="2026-03-03T00:00:00+00:00"))
        d2 = build_data(self.cfg, t2, {}, {"started_at": "1999-01-01T00:00:00+00:00"})
        self.assertEqual(d2["experiment_started_at"], "2026-03-01T00:00:00+00:00")

        started = threading.Event()
        release = threading.Event()
        seen = {}

        def hold():
            with self.tree.lock:
                started.set()
                release.wait(timeout=5)
                self.tree.update(self.tree.get("n001"), title="after-lock", score=99.0)

        def build():
            seen["data"] = build_data(self.cfg, self.tree, {}, {})

        holder = threading.Thread(target=hold)
        builder = threading.Thread(target=build)
        holder.start()
        self.assertTrue(started.wait(2))
        builder.start()
        builder.join(timeout=0.2)
        self.assertTrue(builder.is_alive())
        release.set()
        builder.join(timeout=5)
        holder.join(timeout=5)
        self.assertFalse(builder.is_alive())
        snap = seen["data"]
        node = next(x for x in snap["nodes"] if x["id"] == "n001")
        self.assertEqual(node["title"], "after-lock")
        self.assertEqual(node["score"], 99.0)
        self.assertEqual(snap["best"], "n001")
        self.assertEqual(snap["best"], next(x["id"] for x in snap["nodes"] if x["score"] == max(
            y["score"] for y in snap["nodes"] if y["score"] is not None and y["status"] == "done")))

    def test_template_tokens_in_evidence_remain_literal(self):
        data = build_data(self.cfg, self.tree, {}, {})
        data["insights"] = '__BACK__ __SCRIPTS__ </script><script>bad()</script>'
        page = render_html(data, title="__SCRIPTS__", back_link="/notes/")
        self.assertEqual(_payload_json(page)["insights"], data["insights"])
        self.assertIn("<title>__SCRIPTS__</title>", page)
        self.assertNotIn("</script><script>bad()", page)

    def test_invalid_start_falls_back_to_valid_normalized_dates(self):
        self.tree.meta["created_at"] = "not a timestamp"
        self.tree.get("root").created_at = "2026-01-01T02:00:00+02:00"
        self.tree.get("root").started_at = "invalid"
        data = build_data(self.cfg, self.tree, {}, {"started_at": "2099-01-01T00:00:00Z"})
        self.assertEqual(data["experiment_started_at"], "2026-01-01T00:00:00+00:00")

    def test_payload_survives_nan_in_old_scores(self):
        self.assertFalse(math.isfinite(float("nan")))
        data = build_data(self.cfg, self.tree, {}, {})
        data["nodes"][0]["score"] = float("nan")
        page = render_html(data)
        parsed = _payload_json(page)
        self.assertIsNone(parsed["nodes"][0]["score"])


if __name__ == "__main__":
    unittest.main()
