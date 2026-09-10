"""The loop: set up the root, schedule nodes, supervise workers, stop, report. No LLM sits idle in this loop;
LLMs are invoked only inside node workers and utility calls."""
from __future__ import annotations

import json
import os
import shutil
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, Future
from pathlib import Path
from typing import Any

from . import gitops
from .agents import Utility
from .config import ExperimentCfg
from .evaluator import run_eval, score_of, EvalError
from .render import render_all
from .runner import make_runner, RunResult
from .scheduler import Scheduler
from .tree import Node, Tree
from .util import append_jsonl, atomic_write_json, now_iso, now_ts, read_json, fmt_score, human_duration, read_text
from .worker import run_node


class Orchestrator:
    def __init__(self, cfg: ExperimentCfg, verbose: bool = True):
        self.cfg = cfg
        self.verbose = verbose
        self.started_ts = now_ts()
        self.worker_runner = make_runner(cfg.runner.kind, cfg.runner.model, cfg.runner.effort, cfg.runner.extra_args)
        self.utility_runner = make_runner(cfg.utility.kind, cfg.utility.model, cfg.utility.effort)
        self.tree = self._load_or_create_tree()
        self.utility = Utility(self)
        self.scheduler = Scheduler(self)
        self._cost_lock = threading.Lock()
        self.costs = read_json(cfg.dir / "costs.json", {}) or {}
        self.stop_flag = threading.Event()
        self.render_lock = threading.Lock()

    # infrastructure ----------------------------------------------------------
    def _load_or_create_tree(self) -> Tree:
        if self.cfg.tree_path.exists():
            return Tree.load(self.cfg.tree_path)
        t = Tree(self.cfg.tree_path, meta={"experiment": self.cfg.name, "task": self.cfg.task.name,
                                           "higher_is_better": self.cfg.task.higher_is_better,
                                           "score_key": self.cfg.task.score_key, "created_at": now_iso(),
                                           "runner": f"{self.cfg.runner.kind}:{self.cfg.runner.model}:{self.cfg.runner.effort}",
                                           "reference_scores": self.cfg.task.reference_scores,
                                           "harness_commit": _harness_commit()})
        t.save()
        return t

    def log(self, event: str, **kw: Any) -> None:
        rec = {"t": now_iso(), "event": event, **kw}
        append_jsonl(self.cfg.events_path, rec)
        if self.verbose:
            extras = " ".join(f"{k}={_short(v)}" for k, v in kw.items())
            print(f"[{rec['t'][11:19]}] {event:<16} {extras}", flush=True)

    def add_cost(self, kind: str, res: RunResult) -> None:
        with self._cost_lock:
            c = self.costs.setdefault(kind, {"calls": 0, "cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0, "seconds": 0.0})
            c["calls"] += 1
            c["cost_usd"] += float(res.cost_usd or 0.0)
            u = res.usage or {}
            c["input_tokens"] += int(u.get("input_tokens", u.get("input", 0)) or 0)
            c["output_tokens"] += int(u.get("output_tokens", u.get("output", 0)) or 0)
            c["seconds"] += float(res.duration_s or 0.0)
            atomic_write_json(self.cfg.dir / "costs.json", self.costs)

    def render(self) -> None:
        with self.render_lock:
            try:
                render_all(self.cfg, self.tree, self.costs, self.state())
            except Exception:
                append_jsonl(self.cfg.events_path, {"t": now_iso(), "event": "render_error", "trace": traceback.format_exc()[-2000:]})

    def state(self) -> dict[str, Any]:
        return {"pid": os.getpid(), "started_at": self.started_ts, "heartbeat": now_ts(), "status": getattr(self, "_status", "running"),
                "stop_reason": getattr(self, "_stop_reason", None), "experiment": self.cfg.name}

    def write_state(self) -> None:
        atomic_write_json(self.cfg.dir / "state.json", self.state())

    def noise_level(self) -> float:
        root = self.tree.get("root")
        sem = root.metrics.get("score_sem")
        if isinstance(sem, (int, float)) and sem > 0:
            return 2.0 * float(sem)
        return abs(root.score or 1.0) * 0.01

    # root ---------------------------------------------------------------------
    def ensure_root(self) -> None:
        cfg = self.cfg
        if not (cfg.repo_dir / ".git").exists():
            self.log("repo_init", repo=str(cfg.repo_dir))
            _populate_repo(cfg)
            sha = gitops.init_repo(cfg.repo_dir)
            gitops.tag(cfg.repo_dir, "rsi/root", sha)
        if not cfg.insights_path.exists():
            cfg.insights_path.write_text("# Insights (verified across nodes; each line cites the node)\n\n", encoding="utf-8")
        if not cfg.deadends_path.exists():
            cfg.deadends_path.write_text("# Dead ends (do not retry; each line cites the node)\n\n", encoding="utf-8")
        if "root" not in self.tree.nodes:
            sha = gitops.head(cfg.repo_dir)
            nd = cfg.nodes_dir / "root"
            nd.mkdir(parents=True, exist_ok=True)
            score, metrics = None, {}
            if cfg.search.root_eval:
                self.log("root_eval", seedset=cfg.task.official_seedset)
                metrics = run_eval(cfg, cfg.repo_dir, cfg.task.official_seedset, nd / "eval")
                score = score_of(cfg, metrics)
                self.log("root_eval_done", score=score, elapsed_s=metrics.get("_eval", {}).get("elapsed_s"))
            root = Node(id="root", parent=None, depth=0, title="baseline", hypothesis="The untouched starter code.",
                        kind="baseline", status="done", commit=sha, base_commit=sha, score=score,
                        metrics={k: v for k, v in metrics.items() if k != "per_seed"}, finished_at=now_iso(),
                        summary=f"Baseline starter code. Official {cfg.task.score_key}: {fmt_score(score)}.", verdict="baseline")
            self.tree.add(root)
        root = self.tree.get("root")
        if not root.proposals:
            k = cfg.search.width_root
            self.log("planner_root", k=k)
            props = self.utility.plan_root(k)
            if not props:
                raise RuntimeError("root planner returned no proposals")
            self.tree.update(root, proposals=props)
            self.log("planner_root_done", n=len(props), titles=[p["title"] for p in props])
        self.render()

    # crash recovery -----------------------------------------------------------
    def recover(self) -> None:
        for n in self.tree.by_status("running", "evaluating"):
            self.log("recover_stale", node=n.id, status=n.status)
            nd = self.cfg.nodes_dir / n.id
            wt = self.cfg.worktrees_dir / n.id
            commit = None
            if wt.exists():
                try:
                    commit = gitops.commit_all(wt, f"rsi: recovered uncommitted work of {n.id}") or gitops.head(wt)
                except Exception:
                    commit = None
            diagnosis = {"cause": "The harness process stopped while this node was running.", "retry": True,
                         "advice": "The previous attempt was interrupted by a harness restart, not by a bug in the approach. "
                                   "Read PROGRESS.md of the previous attempt and continue from its last commit."}
            self.tree.update(n, status="failed", failure="harness restarted while node was running", commit=commit,
                             diagnosis=diagnosis, finished_at=now_iso(), verdict="failed",
                             summary="FAILED: harness restarted while running (will retry)")
            (nd / "FAILURE.md").write_text("harness restarted while node was running\n", encoding="utf-8")
        for n in self.tree.by_status("planned"):
            # planned nodes are re-launched as they are
            pass

    # main loop ------------------------------------------------------------------
    def run(self) -> str:
        cfg = self.cfg
        self._status = "running"
        self.write_state()
        self.ensure_root()
        self.recover()
        s = cfg.search
        futures: dict[str, Future] = {}
        stop_reason: str | None = None
        with ThreadPoolExecutor(max_workers=max(1, s.max_parallel), thread_name_prefix="node") as pool:
            # relaunch planned nodes left over from a previous run
            for n in self.tree.by_status("planned"):
                futures[n.id] = pool.submit(self._safe_run_node, n)
            while True:
                for nid, f in list(futures.items()):
                    if f.done():
                        futures.pop(nid)
                if self.stop_flag.is_set():
                    stop_reason = "interrupted"
                if stop_reason is None:
                    stop_reason = self.scheduler.stop_reason()
                    if stop_reason:
                        self.log("stop_condition", reason=stop_reason, in_flight=len(futures))
                if stop_reason is None:
                    launched = 0
                    while len(futures) < s.max_parallel and self.scheduler.can_launch():
                        node = self.scheduler.next_node()
                        if node is None:
                            break
                        futures[node.id] = pool.submit(self._safe_run_node, node)
                        launched += 1
                    if not futures and launched == 0:
                        stop_reason = "exhausted" if self.scheduler.can_launch() else "max_nodes"
                        self.log("stop_condition", reason=stop_reason)
                if stop_reason and not futures:
                    break
                self.write_state()
                time.sleep(3.0)
        self._stop_reason = stop_reason
        self._status = "finishing"
        self.write_state()
        self.finish(stop_reason or "unknown")
        self._status = "finished"
        self.write_state()
        self.render()
        return stop_reason or "unknown"

    def _safe_run_node(self, node: Node) -> None:
        try:
            run_node(self, node)
        except Exception:
            self.log("node_crash", node=node.id, trace=traceback.format_exc()[-1500:])
            try:
                self.tree.update(node, status="failed", failure="harness exception (see events.jsonl)", finished_at=now_iso(),
                                 verdict="failed", diagnosis={"retry": False, "cause": "harness exception", "advice": ""})
            except Exception:
                pass

    # finish -------------------------------------------------------------------------
    def finish(self, reason: str) -> None:
        cfg = self.cfg
        best = self.tree.best()
        root = self.tree.get("root")
        final: dict[str, Any] = {"stop_reason": reason, "finished_at": now_iso(), "best": best.id if best else None,
                                 "elapsed_s": round(now_ts() - self.started_ts, 1)}
        if best is not None and best.id != "root" and cfg.task.final_seedset:
            wt = cfg.worktrees_dir / best.id
            if wt.exists():
                try:
                    self.log("final_eval", node=best.id, seedset=cfg.task.final_seedset)
                    m = run_eval(cfg, wt, cfg.task.final_seedset, cfg.nodes_dir / best.id / "eval", tag="final")
                    final["best_final_score"] = score_of(cfg, m)
                    final["best_final_metrics"] = {k: v for k, v in m.items() if k != "per_seed"}
                    rm = run_eval(cfg, cfg.repo_dir, cfg.task.final_seedset, cfg.nodes_dir / "root" / "eval", tag="final")
                    final["root_final_score"] = score_of(cfg, rm)
                    self.log("final_eval_done", best=final["best_final_score"], root=final["root_final_score"])
                except EvalError as e:
                    final["final_eval_error"] = str(e)
                    self.log("final_eval_failed", error=str(e))
        atomic_write_json(cfg.dir / "final.json", final)
        _write_report(self, final)
        self.log("finished", reason=reason, best=best.id if best else None, best_score=best.score if best else None)


def _harness_commit() -> str:
    try:
        return gitops.git(["rev-parse", "--short", "HEAD"], cwd=Path(__file__).resolve().parents[1], check=False)
    except Exception:
        return ""


def _short(v: Any) -> str:
    s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
    return s if len(s) <= 100 else s[:97] + "..."


def _populate_repo(cfg: ExperimentCfg) -> None:
    repo, task = cfg.repo_dir, cfg.task_dir
    repo.mkdir(parents=True, exist_ok=True)
    starter = task / cfg.task.starter_dir
    if starter.exists():
        shutil.copytree(starter, repo, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".venv"))
    ev = task / cfg.task.eval_dir
    if ev.exists():
        shutil.copytree(ev, repo / "eval", dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    docs = repo / "docs"
    docs.mkdir(exist_ok=True)
    for d in cfg.task.docs:
        src = task / d
        if src.exists():
            shutil.copy2(src, docs / src.name)
    brief = task / cfg.task.brief
    if brief.exists():
        shutil.copy2(brief, repo / "TASK.md")
    gi = repo / ".gitignore"
    if not gi.exists():
        gi.write_text("__pycache__/\n*.pyc\nmetrics*.json\n*.log\n.venv/\n", encoding="utf-8")


def _write_report(o: Orchestrator, final: dict[str, Any]) -> None:
    cfg, tree = o.cfg, o.tree
    best = tree.best()
    root = tree.get("root")
    lines = [f"# pi-rsi report: {cfg.name}", "",
             f"- task: {cfg.task.name}; metric `{cfg.task.score_key}` ({'higher' if cfg.task.higher_is_better else 'lower'} is better)",
             f"- worker: {cfg.runner.kind}:{cfg.runner.model} ({cfg.runner.effort}); utility: {cfg.utility.kind}:{cfg.utility.model}",
             f"- search: width_root={cfg.search.width_root} width={cfg.search.width} depth={cfg.search.depth} max_nodes={cfg.search.max_nodes} parallel={cfg.search.max_parallel} patience={cfg.search.patience}",
             f"- stop reason: {final.get('stop_reason')}; elapsed {human_duration(final.get('elapsed_s'))}",
             f"- baseline (root) official score: {fmt_score(root.score)}",
             f"- best node: `{best.id if best else '-'}` official score {fmt_score(best.score if best else None)}",
             ]
    if "best_final_score" in final:
        lines.append(f"- held-out `{cfg.task.final_seedset}` seed set: best {fmt_score(final['best_final_score'])} vs baseline {fmt_score(final.get('root_final_score'))}")
    if cfg.task.reference_scores:
        lines.append("- reference scores: " + ", ".join(f"{k} {fmt_score(v)}" for k, v in cfg.task.reference_scores.items()))
    costs = o.costs
    if costs:
        lines.append("- cost: " + "; ".join(f"{k}: {v['calls']} calls, ${v['cost_usd']:.2f}, {human_duration(v['seconds'])}" for k, v in costs.items()))
    lines += ["", "## Best path", ""]
    if best:
        for n in tree.ancestors(best.id) + [best]:
            lines.append(f"- `{n.id}` {fmt_score(n.score)} — {n.title}: {n.summary}")
    lines += ["", "## All nodes", "", "| id | parent | depth | status | verdict | score | Δparent | title | duration |", "|---|---|---|---|---|---|---|---|---|"]
    for n in sorted(tree.nodes.values(), key=lambda n: (n.id != "root", n.id)):
        lines.append(f"| {n.id} | {n.parent or '-'} | {n.depth} | {n.status} | {n.verdict or '-'} | {fmt_score(n.score)} | {fmt_score(n.delta_parent)} | {n.title} | {human_duration(n.duration_s)} |")
    lines += ["", "## Insights", "", read_text(cfg.insights_path).strip() or "(none)", "", "## Dead ends", "",
              read_text(cfg.deadends_path).strip() or "(none)", ""]
    (cfg.dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
