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
    exp_dir = Path(a.dir).resolve()
    if (exp_dir / "rsi.toml").exists() and not a.force:
        print(f"{exp_dir} already initialized (use --force to overwrite rsi.toml)", file=sys.stderr)
        return 1
    task = load_task_cfg(Path(a.task).resolve())
    runner = RunnerCfg(kind=a.runner, model=a.model, effort=a.effort, max_turns=a.max_turns,
                       node_timeout_s=a.node_timeout, idle_timeout_s=a.idle_timeout)
    utility = UtilityCfg(kind=a.utility_runner or a.runner, model=a.utility_model or a.model, effort=a.utility_effort)
    search = SearchCfg(width_root=a.width_root, width=a.width, depth=a.depth, max_nodes=a.max_nodes,
                       max_parallel=a.parallel, patience=a.patience, target_score=a.target,
                       max_wallclock_s=a.max_wallclock)
    cfg = ExperimentCfg(name=a.name or exp_dir.name, dir=exp_dir, task=task, runner=runner, utility=utility, search=search,
                        notes=a.notes or "")
    exp_dir.mkdir(parents=True, exist_ok=True)
    write_experiment_toml(cfg)
    print(f"initialized {exp_dir}\n" + (exp_dir / "rsi.toml").read_text())
    return 0


def cmd_run(a: argparse.Namespace) -> int:
    from .orchestrator import Orchestrator
    cfg = load_experiment(Path(a.dir))
    orch = Orchestrator(cfg, verbose=not a.quiet)

    def _sig(signum, frame):
        orch.log("signal", signum=signum)
        orch.stop_flag.set()

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)
    reason = orch.run()
    print(f"finished: {reason}; see {cfg.dir / 'REPORT.md'} and {cfg.dir / 'tree.html'}")
    return 0


def cmd_render(a: argparse.Namespace) -> int:
    from .render import render_all
    from .tree import Tree
    cfg = load_experiment(Path(a.dir))
    tree = Tree.load(cfg.tree_path)
    render_all(cfg, tree, read_json(cfg.dir / "costs.json", {}) or {}, read_json(cfg.dir / "state.json", {}) or {})
    print(cfg.dir / "tree.html")
    return 0


def cmd_status(a: argparse.Namespace) -> int:
    from .tree import Tree
    cfg = load_experiment(Path(a.dir))
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
    cfg = load_experiment(Path(a.dir))
    wt = Path(a.worktree).resolve() if a.worktree else cfg.repo_dir
    m = run_eval(cfg, wt, a.seedset or cfg.task.official_seedset, Path(a.out).resolve() if a.out else cfg.dir / "adhoc_eval")
    print(json.dumps({k: v for k, v in m.items() if k != "per_seed"}, indent=1))
    print("score", score_of(cfg, m))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="rsi", description="pi-rsi auto-research harness")
    sub = p.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("init", help="create an experiment directory with rsi.toml")
    i.add_argument("dir")
    i.add_argument("--task", required=True, help="task pack directory (contains task.toml)")
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
    i.add_argument("--notes", default="")
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

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
