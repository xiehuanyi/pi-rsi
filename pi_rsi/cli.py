"""rsi command line: init an experiment, run/resume it, render, status."""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
from pathlib import Path

from .config import ExperimentCfg, RunnerCfg, UtilityCfg, SearchCfg, load_task_cfg, load_experiment, write_experiment_toml
from .util import read_json, fmt_score, human_duration

ROOT = Path(__file__).resolve().parents[1]


def cmd_init(a: argparse.Namespace) -> int:
    from .home import experiments_dir
    exp_dir = Path(a.dir).expanduser()
    if not exp_dir.is_absolute() and "/" not in a.dir:
        exp_dir = experiments_dir() / a.dir     # bare name -> experiments directory
    exp_dir = exp_dir.resolve()
    if (exp_dir / "rsi.toml").exists() and not a.force:
        print(f"{exp_dir} already initialized (use --force to overwrite rsi.toml)", file=sys.stderr)
        return 1
    from .home import resolve_task
    task = load_task_cfg(resolve_task(a.task))
    runner = RunnerCfg(kind=a.runner, model=a.model, effort=a.effort, max_turns=a.max_turns,
                       node_timeout_s=a.node_timeout, idle_timeout_s=a.idle_timeout)
    utility = UtilityCfg(kind=a.utility_runner or a.runner, model=a.utility_model or a.model, effort=a.utility_effort)
    search = SearchCfg(width_root=a.width_root, width=a.width, depth=a.depth, max_nodes=a.max_nodes,
                       max_parallel=a.parallel, patience=a.patience, target_score=a.target,
                       max_wallclock_s=a.max_wallclock, max_gpu_hours=a.max_gpu_hours)
    from .config import HooksCfg
    hooks = HooksCfg(on_finish=a.on_finish, narrative=not a.no_narrative)
    cfg = ExperimentCfg(name=a.name or exp_dir.name, dir=exp_dir, task=task, runner=runner, utility=utility, search=search,
                        hooks=hooks, notes=a.notes or "")
    exp_dir.mkdir(parents=True, exist_ok=True)
    write_experiment_toml(cfg)
    print(f"initialized {exp_dir}\n" + (exp_dir / "rsi.toml").read_text())
    return 0


def _exp(dir_arg: str) -> Path:
    from .home import experiments_dir
    p = Path(dir_arg).expanduser()
    if not (p / "rsi.toml").exists() and "/" not in dir_arg and (experiments_dir() / dir_arg / "rsi.toml").exists():
        return experiments_dir() / dir_arg
    return p


def cmd_run(a: argparse.Namespace) -> int:
    from .orchestrator import Orchestrator
    cfg = load_experiment(_exp(a.dir))
    orch = Orchestrator(cfg, verbose=not a.quiet)

    def _sig(signum, frame):
        orch.log("signal", signum=signum)
        orch.stop_flag.set()

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)
    reason = orch.run()
    print(f"finished: {reason}; see {cfg.dir / 'REPORT.md'} and {cfg.dir / 'tree.html'}")
    return 0


def cmd_task(a: argparse.Namespace) -> int:
    from .home import list_bundled, install_task, tasks_dir
    if a.action == "list":
        for n in list_bundled():
            print(n, "(installed)" if (tasks_dir() / n / ".venv").exists() else "")
        return 0
    dst = install_task(a.name, force=a.force, setup=not a.no_setup)
    print(f"task pack ready at {dst}")
    return 0


def cmd_ops(a: argparse.Namespace) -> int:
    from .orchestrator import Orchestrator
    from .ops import run_ops
    cfg = load_experiment(_exp(a.dir))
    orch = Orchestrator(cfg, verbose=True)
    evidence = Path(a.evidence).read_text(encoding="utf-8") if a.evidence else ""
    v = run_ops(orch, a.problem, evidence, max_turns=cfg.ops.max_turns, timeout_s=cfg.ops.timeout_s)
    print(json.dumps({k: v[k] for k in ("fixed", "retry_failed_nodes", "summary", "dir") if k in v}, indent=1, ensure_ascii=False))
    return 0 if v.get("fixed") else 1


def cmd_write(a: argparse.Namespace) -> int:
    from .orchestrator import Orchestrator
    from .ops import write_narrative
    cfg = load_experiment(_exp(a.dir))
    orch = Orchestrator(cfg, verbose=True)
    text = write_narrative(orch, a.language or cfg.hooks.narrative_language)
    print(text[:2000])
    return 0 if text else 1


def cmd_relabel(a: argparse.Namespace) -> int:
    """Recompute verdicts from official scores with the paired noise estimate (keeps auditor summaries)."""
    from .orchestrator import Orchestrator
    cfg = load_experiment(_exp(a.dir))
    orch = Orchestrator(cfg, verbose=False)
    tree = orch.tree
    changed = 0
    for n in tree.non_root():
        if n.status != "done" or n.score is None or not n.parent:
            continue
        parent = tree.get(n.parent)
        m1 = read_json(cfg.nodes_dir / n.id / "eval" / f"metrics.{cfg.task.official_seedset}.json") or n.metrics
        m2 = read_json(cfg.nodes_dir / parent.id / "eval" / f"metrics.{cfg.task.official_seedset}.json") or parent.metrics
        noise = orch.noise_level(m1, m2)
        d = (n.score - parent.score) if cfg.task.higher_is_better else (parent.score - n.score)
        verdict = "improved" if d > noise else ("worse" if d < -noise else "no_change")
        if verdict != n.verdict:
            changed += 1
            print(f"{n.id}: {n.verdict} -> {verdict} (delta {d:+.5g}, noise {noise:.4g})")
            audit = dict(n.audit or {}); audit["verdict"] = verdict; audit["relabel_note"] = f"paired noise {noise:.4g}"
            tree.update(n, verdict=verdict, audit=audit)
    orch.render()
    print(f"relabeled {changed} nodes")
    return 0


def cmd_submit(a: argparse.Namespace) -> int:
    from .orchestrator import Orchestrator
    from .logistics import submit, submissions
    cfg = load_experiment(_exp(a.dir))
    orch = Orchestrator(cfg, verbose=True)
    if a.list:
        for r in submissions(cfg):
            print(f"{r['time']} {r['node']} {fmt_score(r['score'])} {r['file']}")
        return 0
    row = submit(cfg, orch.tree, a.node, cfg.hooks.max_submissions)
    print(json.dumps(row, indent=1))
    return 0


def cmd_sentinel(a: argparse.Namespace) -> int:
    from .home import experiments_dir
    from .logistics import sentinel
    root = Path(a.root).resolve() if a.root else experiments_dir()
    while True:
        rep = sentinel(root, prune=a.prune, kill_orphans=a.kill_orphans)
        print(json.dumps(rep, indent=1, ensure_ascii=False))
        if not a.interval:
            return 0
        import time as _t
        _t.sleep(a.interval)


def cmd_repair(a: argparse.Namespace) -> int:
    from .orchestrator import Orchestrator
    from .logistics import collect_crashes, repair
    cfg = load_experiment(_exp(a.dir))
    orch = Orchestrator(cfg, verbose=True)
    evidence = collect_crashes(cfg)
    v = repair(orch, evidence, a.branch)
    print(json.dumps({k: v.get(k) for k in ("fixed", "summary", "branch", "diffstat", "dir")}, indent=1, ensure_ascii=False))
    return 0 if v.get("fixed") else 1


def cmd_newtask(a: argparse.Namespace) -> int:
    from .newtask import new_task
    answers = json.loads(Path(a.answers).read_text()) if a.answers else None
    new_task(a.name, a.problem, a.data, a.runner, a.model, a.effort, a.utility_model, a.utility_effort, yes=a.yes,
             answers=answers, max_turns=a.max_turns, timeout_s=a.timeout)
    return 0


def cmd_jobd(a: argparse.Namespace) -> int:
    from .jobs import run_daemon, default_gpus
    gpus = [int(x) for x in a.gpus.split(",") if x.strip()] if a.gpus is not None else default_gpus()
    run_daemon(gpus, max_cpu_jobs=a.max_cpu_jobs)
    return 0


def cmd_jobs(a: argparse.Namespace) -> int:
    from .jobs import list_jobs, cancel, daemon_alive, jobs_dir
    if a.cancel:
        cancel(a.cancel)
        print("cancel requested", a.cancel)
        return 0
    print(f"daemon alive: {daemon_alive()}  dir: {jobs_dir()}")
    for j in list_jobs(a.status):
        print(f"{j.id} {j.status:<8} {j.owner:<28} gpus={j.assigned_gpus or j.gpus} step={j.last_step} value={j.last_value} "
              f"{human_duration(j.duration_s)} {j.reason}")
    return 0


def cmd_continue(a: argparse.Namespace) -> int:
    """Extend a finished (or stopped) experiment: raise budgets, reset the stall counter, optionally pin the next
    expansions to one node and leave a note for the workers and planners. Then `rsi run` (or --run)."""
    import re
    from .tree import Tree
    from .util import now_iso, append_jsonl
    exp = _exp(a.dir)
    cfg = load_experiment(exp)
    toml_path = exp / "rsi.toml"
    text = toml_path.read_text(encoding="utf-8")

    def set_key(section: str, key: str, value):
        nonlocal text
        pat = re.compile(rf"(\[{section}\][^\[]*?^{key}\s*=\s*)([^\n]*)$", re.S | re.M)
        if pat.search(text):
            text = pat.sub(lambda m: m.group(1) + repr(value), text, count=1)
        else:
            text = text.replace(f"[{section}]\n", f"[{section}]\n{key} = {value!r}\n", 1)

    if a.max_nodes:
        new = cfg.search.max_nodes + int(a.max_nodes[1:]) if a.max_nodes.startswith("+") else int(a.max_nodes)
        set_key("search", "max_nodes", new)
    if a.patience is not None:
        set_key("search", "patience", int(a.patience))
    if a.max_wallclock is not None:
        set_key("search", "max_wallclock_s", int(a.max_wallclock))
    if a.depth is not None:
        set_key("search", "depth", int(a.depth))
    if a.width is not None:
        set_key("search", "width", int(a.width))
    toml_path.write_text(text, encoding="utf-8")
    tree = Tree.load(cfg.tree_path)
    tree.meta["continue_from"] = now_iso()
    tree.meta["focus"] = a.from_node or None
    tree.save()
    if a.note:
        with open(exp / "HUMAN.md", "a", encoding="utf-8") as f:
            f.write(f"\n[{now_iso()}] {a.note}\n")
    append_jsonl(cfg.events_path, {"t": now_iso(), "event": "continued", "max_nodes": a.max_nodes, "patience": a.patience,
                                   "focus": a.from_node, "note": a.note})
    cfg = load_experiment(exp)
    print(f"continue: max_nodes={cfg.search.max_nodes} patience={cfg.search.patience} depth={cfg.search.depth} width={cfg.search.width} "
          f"focus={a.from_node or '-'}; stall counter reset")
    if a.run:
        return cmd_run(argparse.Namespace(dir=str(exp), quiet=a.quiet))
    print(f"now: rsi run {exp}")
    return 0


def cmd_reeval(a: argparse.Namespace) -> int:
    """Re-run the official evaluator on the root and every done node (e.g. after an evaluator fix); scores are
    expected to be unchanged for deterministic pipelines, metrics files gain any new fields (per_item)."""
    from .evaluator import run_eval, score_of
    from .orchestrator import Orchestrator
    cfg = load_experiment(_exp(a.dir))
    orch = Orchestrator(cfg, verbose=False)
    tree = orch.tree
    for n in sorted(tree.nodes.values(), key=lambda n: (n.id != "root", n.id)):
        if n.status != "done":
            continue
        wt = cfg.repo_dir if n.id == "root" else cfg.worktrees_dir / n.id
        if not wt.exists():
            print(f"{n.id}: worktree missing, skipped"); continue
        m = run_eval(cfg, wt, cfg.task.official_seedset, cfg.nodes_dir / n.id / "eval")
        s = score_of(cfg, m)
        print(f"{n.id}: {n.score} -> {s}{'' if s == n.score else '  (CHANGED)'}")
        tree.update(n, score=s, metrics={k: v for k, v in m.items() if k not in ("per_seed", "per_item")})
    orch.render()
    return 0


def cmd_report(a: argparse.Namespace) -> int:
    from .orchestrator import Orchestrator, _write_report
    cfg = load_experiment(_exp(a.dir))
    orch = Orchestrator(cfg, verbose=False)
    _write_report(orch, read_json(cfg.dir / "final.json", {}) or {})
    orch.render()
    print(cfg.dir / "REPORT.md")
    return 0


def cmd_render(a: argparse.Namespace) -> int:
    from .render import render_all
    from .tree import Tree
    cfg = load_experiment(_exp(a.dir))
    tree = Tree.load(cfg.tree_path)
    render_all(cfg, tree, read_json(cfg.dir / "costs.json", {}) or {}, read_json(cfg.dir / "state.json", {}) or {})
    print(cfg.dir / "tree.html")
    return 0


def cmd_status(a: argparse.Namespace) -> int:
    from .tree import Tree
    cfg = load_experiment(_exp(a.dir))
    if not cfg.tree_path.exists():
        print("no tree yet")
        return 0
    tree = Tree.load(cfg.tree_path)
    st = read_json(cfg.dir / "state.json", {}) or {}
    best = tree.best()
    print(f"experiment {cfg.name} [{cfg.runner.kind}:{cfg.runner.model}] state={st.get('status')} stop={st.get('stop_reason')}")
    print(f"baseline {fmt_score(tree.get('root').score)}  best {best.id if best else '-'} {fmt_score(best.score if best else None)}")
    for n in sorted(tree.nodes.values(), key=lambda n: (n.id != 'root', n.id)):
        print(f"  {n.id:<6} p={n.parent or '-':<5} d={n.depth} {n.status:<10} {n.verdict or '-':<10} {fmt_score(n.score):>10} "
              f"Δp={fmt_score(n.delta_parent):>8} {human_duration(n.duration_s):>7}  {n.title}")
    return 0


def cmd_eval(a: argparse.Namespace) -> int:
    from .evaluator import run_eval, score_of
    cfg = load_experiment(_exp(a.dir))
    wt = Path(a.worktree).resolve() if a.worktree else cfg.repo_dir
    m = run_eval(cfg, wt, a.seedset or cfg.task.official_seedset, Path(a.out).resolve() if a.out else cfg.dir / "adhoc_eval")
    print(json.dumps({k: v for k, v in m.items() if k != "per_seed"}, indent=1))
    print("score", score_of(cfg, m))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="rsi", description="pi-rsi auto-research harness")
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("task", help="list or install bundled task packs")
    t.add_argument("action", choices=["list", "install"])
    t.add_argument("name", nargs="?")
    t.add_argument("--force", action="store_true")
    t.add_argument("--no-setup", action="store_true")
    t.set_defaults(fn=cmd_task)

    i = sub.add_parser("init", help="create an experiment directory with rsi.toml")
    i.add_argument("dir", help="experiment directory, or a bare name placed under the experiments directory")
    i.add_argument("--task", required=True, help="task pack directory or bundled task name (see `rsi task list`)")
    i.add_argument("--name")
    i.add_argument("--runner", default="grok", choices=["grok", "pi", "script"])
    i.add_argument("--model", default="grok-4.6")
    i.add_argument("--effort", default="high")
    i.add_argument("--utility-runner", default=None)
    i.add_argument("--utility-model", default=None)
    i.add_argument("--utility-effort", default="low")
    i.add_argument("--max-turns", type=int, default=80)
    i.add_argument("--node-timeout", type=int, default=1800, help="seconds of wall-clock per worker session")
    i.add_argument("--idle-timeout", type=int, default=420)
    i.add_argument("--width-root", type=int, default=3)
    i.add_argument("--width", type=int, default=2)
    i.add_argument("--depth", type=int, default=4)
    i.add_argument("--max-nodes", type=int, default=12)
    i.add_argument("--parallel", type=int, default=2)
    i.add_argument("--patience", type=int, default=4)
    i.add_argument("--target", type=float, default=None)
    i.add_argument("--max-wallclock", type=int, default=None)
    i.add_argument("--max-gpu-hours", type=float, default=None)
    i.add_argument("--notes", default="")
    i.add_argument("--on-finish", default="", help="shell command run after the final report; {exp_dir} is substituted")
    i.add_argument("--no-narrative", action="store_true")
    i.add_argument("--force", action="store_true")
    i.set_defaults(fn=cmd_init)

    r = sub.add_parser("run", help="run or resume an experiment")
    r.add_argument("dir")
    r.add_argument("--quiet", action="store_true")
    r.set_defaults(fn=cmd_run)

    s = sub.add_parser("status", help="print the tree")
    s.add_argument("dir")
    s.set_defaults(fn=cmd_status)

    v = sub.add_parser("render", help="re-render tree.html and tree.md")
    v.add_argument("dir")
    v.set_defaults(fn=cmd_render)

    e = sub.add_parser("eval", help="run the frozen evaluator on a worktree")
    e.add_argument("dir")
    e.add_argument("--worktree")
    e.add_argument("--seedset")
    e.add_argument("--out")
    e.set_defaults(fn=cmd_eval)

    o = sub.add_parser("ops", help="run the ops (logistics) agent on a problem")
    o.add_argument("dir")
    o.add_argument("problem")
    o.add_argument("--evidence", help="file with logs to include")
    o.set_defaults(fn=cmd_ops)

    sb = sub.add_parser("submit", help="final-level evaluation (e.g. Kaggle submission) of a node, with a cap and a ledger")
    sb.add_argument("dir")
    sb.add_argument("--node")
    sb.add_argument("--list", action="store_true")
    sb.set_defaults(fn=cmd_submit)

    se = sub.add_parser("sentinel", help="infra check: disk, GPUs, dead orchestrators, orphan processes, stale worktrees")
    se.add_argument("--root", help="experiments directory (default: the configured one)")
    se.add_argument("--interval", type=int, default=0, help="repeat every N seconds")
    se.add_argument("--prune", action="store_true", help="remove worktrees of finished experiments outside the best path")
    se.add_argument("--kill-orphans", action="store_true")
    se.set_defaults(fn=cmd_sentinel)

    rr = sub.add_parser("repair", help="harness self-repair: an ops agent fixes recorded harness crashes on a git branch")
    rr.add_argument("dir")
    rr.add_argument("--branch")
    rr.set_defaults(fn=cmd_repair)

    nt = sub.add_parser("new-task", help="clarification phase: problem statement -> questions -> a verified task pack")
    nt.add_argument("name")
    nt.add_argument("problem", help="one-line problem statement")
    nt.add_argument("--data", help="directory/file to copy, or kaggle:<competition>")
    nt.add_argument("--runner", default="grok", choices=["grok", "pi", "script"])
    nt.add_argument("--model", default="grok-4.6")
    nt.add_argument("--effort", default="high")
    nt.add_argument("--utility-model", default="grok-4.5")
    nt.add_argument("--utility-effort", default="low")
    nt.add_argument("--yes", action="store_true", help="accept the recommended defaults without asking")
    nt.add_argument("--answers", help="JSON file with answers keyed by question id (plus deliverable/metric)")
    nt.add_argument("--max-turns", type=int, default=120)
    nt.add_argument("--timeout", type=int, default=3600)
    nt.set_defaults(fn=cmd_newtask)

    jd = sub.add_parser("jobd", help="run the job queue daemon (GPU assignment, timeouts, early termination)")
    jd.add_argument("--gpus", default=None, help="comma-separated GPU ids (default: all visible)")
    jd.add_argument("--max-cpu-jobs", type=int, default=2)
    jd.set_defaults(fn=cmd_jobd)

    js = sub.add_parser("jobs", help="list queue jobs or cancel one")
    js.add_argument("--status")
    js.add_argument("--cancel")
    js.set_defaults(fn=cmd_jobs)

    c = sub.add_parser("continue", help="extend a finished experiment: more nodes, reset stall counter, optional focus node and note")
    c.add_argument("dir")
    c.add_argument("--max-nodes", help="new total, or +N to add")
    c.add_argument("--patience", type=int)
    c.add_argument("--max-wallclock", type=int)
    c.add_argument("--depth", type=int)
    c.add_argument("--width", type=int)
    c.add_argument("--from", dest="from_node", help="node id whose subtree gets the next expansions")
    c.add_argument("--note", help="a note for the workers and planners (appended to <exp>/HUMAN.md)")
    c.add_argument("--run", action="store_true", help="run immediately")
    c.add_argument("--quiet", action="store_true")
    c.set_defaults(fn=cmd_continue)

    re_ = sub.add_parser("reeval", help="re-run the official evaluator on root and all done nodes")
    re_.add_argument("dir")
    re_.set_defaults(fn=cmd_reeval)

    rp = sub.add_parser("report", help="rewrite REPORT.md and re-render from the current tree/final state")
    rp.add_argument("dir")
    rp.set_defaults(fn=cmd_report)

    rl = sub.add_parser("relabel", help="recompute improved/worse/no_change verdicts with paired noise")
    rl.add_argument("dir")
    rl.set_defaults(fn=cmd_relabel)

    w = sub.add_parser("write", help="write NARRATIVE.md for a finished experiment")
    w.add_argument("dir")
    w.add_argument("--language")
    w.set_defaults(fn=cmd_write)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
