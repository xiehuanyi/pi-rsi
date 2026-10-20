"""rsi command line: init an experiment, run/resume it, render, status."""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
from pathlib import Path

from .config import (ExperimentCfg, RunnerCfg, UtilityCfg, SearchCfg, MemoryCfg, ResearchCfg, MaintainerCfg, SetupCfg,
                     load_task_cfg, load_experiment, write_experiment_toml)
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
                       max_attempts=a.max_attempts,
                       max_parallel=a.parallel, patience=a.patience, target_score=a.target,
                       max_wallclock_s=a.max_wallclock, max_gpu_hours=a.max_gpu_hours)
    from .config import HooksCfg
    hooks = HooksCfg(on_finish=a.on_finish, narrative=not a.no_narrative)
    cfg = ExperimentCfg(name=a.name or exp_dir.name, dir=exp_dir, task=task, runner=runner, utility=utility, search=search,
                        hooks=hooks, memory=MemoryCfg(enabled=not a.no_memory, path=a.memory_dir or ""),
                        research=ResearchCfg(enabled=not a.no_research_loop, kind=a.research_runner or "",
                                             model=a.research_model or "", effort=a.research_effort or "",
                                             timeout_s=a.think_timeout, review_every=a.review_every),
                        maintainer=MaintainerCfg(enabled=not a.no_maintainer, kind=a.maintainer_runner,
                                                 model=a.maintainer_model, effort=a.maintainer_effort),
                        setup=SetupCfg(proxy=a.yolo, calibration_runs=a.calibration_runs),
                        notes=a.notes or "")
    exp_dir.mkdir(parents=True, exist_ok=True)
    write_experiment_toml(cfg)
    print(f"initialized {exp_dir}\n" + (exp_dir / "rsi.toml").read_text())
    if cfg.research.enabled:
        print(f"next: rsi setup {exp_dir}   (calibration, setup review, your answers to the critical questions)")
    return 0


def cmd_setup(a: argparse.Namespace) -> int:
    """Calibrate noise, review the setup and record decisions; the human confirms what only the human may."""
    from .orchestrator import Orchestrator
    exp = _exp(a.dir)
    cfg = load_experiment(exp)
    if not cfg.research.enabled:
        raise ValueError("setup applies to research-loop experiments (rsi research enable first)")
    if a.yolo is not None and a.yolo != cfg.setup.proxy:
        cfg.setup.proxy = a.yolo
        write_experiment_toml(cfg)
    answers = {}
    for item in a.answer or []:
        key, sep, value = item.partition("=")
        if not sep:
            raise ValueError(f"--answer needs id=value, got {item!r}")
        answers[key.strip()] = value.strip()
    orch = Orchestrator(cfg, verbose=not a.quiet)
    orch.ensure_root()

    def ask(q):
        print(f"\n[{q['id']}] ({q['importance']}) {q['question']}")
        print(f"  why: {q['rationale']}")
        for i, option in enumerate(q["options"], 1):
            print(f"  {i}. {option}{'   (recommended)' if option == q['recommended'] else ''}")
        while True:
            raw = input(f"answer [Enter = {q['recommended']}]> ").strip()
            value = q["options"][int(raw) - 1] if raw.isdigit() and 0 < int(raw) <= len(q["options"]) else raw
            value = value or q["recommended"]
            try:
                if q.get("kind") == "number":
                    float(value)
                return value
            except ValueError:
                print("  a number is required")

    status = orch.setup.run(answers=answers, accept_recommended=a.accept_recommended,
                            ask=ask if sys.stdin.isatty() and not a.quiet else None)
    orch.render()
    print((cfg.setup_dir / "SETUP.md").read_text())
    if status != "complete" or (cfg.setup_dir / "QUESTIONS.md").exists():
        print(f"waiting for the human: {cfg.setup_dir / 'QUESTIONS.md'}")
    if status != "complete":
        return 3
    print(f"setup complete; next: rsi run {exp}")
    return 0


def _exp(dir_arg: str) -> Path:
    from .home import experiments_dir
    p = Path(dir_arg).expanduser()
    if not (p / "rsi.toml").exists() and "/" not in dir_arg and (experiments_dir() / dir_arg / "rsi.toml").exists():
        return experiments_dir() / dir_arg
    return p


def cmd_memory(a: argparse.Namespace) -> int:
    from .memory import ResearchMemory
    from .tree import Tree
    cfg = load_experiment(_exp(a.dir))
    if a.action in ("enable", "disable"):
        cfg.memory.enabled = a.action == "enable"
        if a.path:
            cfg.memory.path = a.path
        write_experiment_toml(cfg)
    memory = ResearchMemory(cfg)
    if a.action in ("sync", "reflect", "review", "ingest") and not memory.enabled:
        raise ValueError("memory is disabled; run rsi memory enable <experiment> first")
    if a.action in ("sync", "reflect", "review"):
        memory.sync(Tree.load(cfg.tree_path))
    if a.action == "ingest":
        if not a.source:
            raise ValueError("ingest requires --source <local UTF-8 text/Markdown file>")
        print("captured", memory.ingest(Path(a.source), a.label or ""))
    if a.action in ("reflect", "review"):
        from .orchestrator import Orchestrator
        orch = Orchestrator(cfg)
        for _ in range(max(1, min(a.batches, 10))):
            # A human request skips the automatic retry backoff and retries set-aside evidence now.
            if not memory.reflect(orch.maintainer, force=True, review=a.action == "review", retry_now=True):
                break
    state = memory.state()
    print(json.dumps({"enabled": memory.enabled, "path": str(memory.root), "revision": state["revision"],
                      "claims": len(state["claims"]), "topics": len(state.get("topics", {})),
                      "pending": len(memory.pending()) if memory.enabled else 0},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_research(a: argparse.Namespace) -> int:
    cfg = load_experiment(_exp(a.dir))
    if a.action == "repair":
        from .orchestrator import Orchestrator
        orch = Orchestrator(cfg)
        print(json.dumps({"repaired_cycle": orch.research.repair_plan(), "new_experiments": 0}))
        return 0
    if a.action in ("enable", "disable"):
        cfg.research.enabled = a.action == "enable"
        if a.action == "enable":
            cfg.memory.enabled = True
            cfg.maintainer.enabled = True
        for name in ("research", "maintainer"):
            role = getattr(cfg, name)
            for key in ("kind", "model", "effort"):
                value = getattr(a, name + "_" + ("runner" if key == "kind" else key))
                if value is not None:
                    setattr(role, key, value)
        if a.review_every is not None:
            cfg.research.review_every = a.review_every
            cfg.research.__post_init__()
        write_experiment_toml(cfg)
    print(json.dumps({"enabled": cfg.research.enabled, "review_every": cfg.research.review_every,
        "execution": "sequential research loop" if cfg.research.enabled else "legacy tree scheduler",
        "researcher": {"runner": cfg.research.kind or cfg.runner.kind,
                       "model": cfg.research.model or cfg.runner.model},
        "maintainer": {"enabled": cfg.maintainer.enabled, "runner": cfg.maintainer.kind,
                       "model": cfg.maintainer.model}}, ensure_ascii=False, indent=2))
    return 0


def cmd_monitor(a: argparse.Namespace) -> int:
    cfg = load_experiment(_exp(a.dir))
    records = []
    if cfg.tree_path.exists():
        from .tree import Tree
        for n in Tree.load(cfg.tree_path).nodes.values():
            if n.status == "waiting":  # the wake queue: tasks the controller polls without a thread or a model
                records.append({"node": n.id, "kind": "waiting_node", **(n.worker.get("waiting") or {})})
    for path in sorted(cfg.nodes_dir.glob("*/eval/*.monitor.json")):
        record = read_json(path, {}) or {}
        # Refresh queue state without calling or waking a model.
        if record.get("job") and not record.get("wake_ready"):
            from .jobs import Job
            try:
                job = Job.load(record["job"])
                record.update(job_state=job.status, reason=job.reason)
            except FileNotFoundError:
                record["job_state"] = "missing"
        records.append({"node": path.parent.parent.name, "path": str(path), **record})
    print(json.dumps(records, ensure_ascii=False, indent=2))
    return 0


def cmd_job(a: argparse.Namespace) -> int:
    """Worker side of long tasks: register a command with the task queue and end the session; the harness
    resumes the session when the job ends. The record lives in <node dir>/jobs/<job id>.json."""
    from . import jobs
    from .util import atomic_write_json, now_iso
    if a.action != "submit":
        raise ValueError("rsi job supports: submit")
    cmd = list(a.cmd)
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        raise ValueError("rsi job submit needs a command after --")
    nd = Path(a.node_dir).expanduser().resolve()
    if not nd.is_dir():
        raise ValueError(f"node directory not found: {nd}")
    exp = nd.parent.parent
    try:
        name = load_experiment(exp).name  # GPU-hour accounting groups jobs by the experiment's name
    except (OSError, ValueError, KeyError):
        name = exp.name
    owner = f"{name}/{nd.name}/worker"
    cwd = Path.cwd()
    result = str(Path(a.result).resolve()) if a.result else ""
    metrics = str(Path(a.metrics).resolve()) if a.metrics else ""
    jobs.ensure_daemon()
    job = jobs.submit(cmd, cwd, owner=owner, gpus=a.gpus, timeout_s=a.timeout, stall_s=a.stall,
                      metrics_path=metrics, result_path=result)
    atomic_write_json(nd / "jobs" / f"{job.id}.json", {
        "job": job.id, "cmd": cmd, "cwd": str(cwd), "submitted_at": now_iso(), "gpus": a.gpus,
        "timeout_s": a.timeout, "result_path": result, "metrics_path": metrics, "label": a.label or ""})
    print(job.id)
    print(f"submitted {job.id}; log {jobs.jobs_dir() / 'logs' / (job.id + '.log')}. End this session now; "
          "the harness resumes it when the job ends.", file=sys.stderr)
    return 0


def cmd_closeout(a: argparse.Namespace) -> int:
    from .orchestrator import Orchestrator
    from .closeout import recover
    cfg=load_experiment(_exp(a.dir));orch=Orchestrator(cfg,verbose=not a.quiet)
    recovered=recover(orch,a.node,seconds=a.seconds)
    print(json.dumps({'recovered':recovered,'new_experiments':0,'best':orch.tree.best_id()},ensure_ascii=False))
    return 0


def cmd_run(a: argparse.Namespace) -> int:
    from .orchestrator import Orchestrator
    cfg = load_experiment(_exp(a.dir))
    state = read_json(cfg.dir / "state.json", {}) or {}
    pid = state.get("pid")
    if state.get("status") in ("running", "finishing") and pid and pid != os.getpid() and Path(f"/proc/{pid}").exists():
        raise ValueError("this experiment already has a live controller; refusing concurrent execution")
    orch = Orchestrator(cfg, verbose=not a.quiet)

    def _sig(signum, frame):
        orch.log("signal", signum=signum)
        orch.stop_flag.set()

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)
    reason = orch.run()
    if reason == "setup_required":
        print(f"this research run needs a confirmed setup first: rsi setup {cfg.dir}")
        return 3
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
    with orch.executions.controller_lease():
        return _relabel(orch)


def _relabel(orch):
    cfg, tree = orch.cfg, orch.tree
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
    if a.max_attempts is not None:
        set_key("search", "max_attempts", int(a.max_attempts))
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
    tree.meta.pop("research_stop", None)
    tree.meta.pop("research_error", None)
    tree.meta.pop("research_decision", None)
    tree.meta.pop("research_proposal", None)  # a human intervention gets a full review
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
    with orch.executions.controller_lease():
        return _reevaluate(orch)


def _reevaluate(orch):
    from .evaluator import run_eval, score_of
    cfg, tree = orch.cfg, orch.tree
    from .measurement import measurement_record
    from .util import now_iso
    orch.executions.migrate(tree)
    for n in sorted(tree.hypotheses(), key=lambda n: (n.id != "root", n.id)):
        # Stale = measured under an earlier evaluation protocol; reeval is how it becomes comparable again.
        if not (n.measurement_valid or n.measurement.get("state") == "stale"):
            continue
        wt = cfg.repo_dir if n.id == "root" else cfg.worktrees_dir / n.id
        if not wt.exists():
            print(f"{n.id}: worktree missing, skipped"); continue
        revision = cfg.nodes_dir / n.id / "measurements" / now_iso().replace(":", "")
        m = run_eval(cfg, wt, cfg.task.official_seedset, revision, owner=f"{cfg.name}/{n.id}/reeval")
        s = score_of(cfg, m)
        print(f"{n.id}: {n.score} -> {s}{'' if s == n.score else '  (CHANGED)'}")
        if s is None:
            raise ValueError("reevaluation did not produce a valid score")
        reference={"state":"validated",**measurement_record(cfg,n,n.commit,s,path=revision/f"metrics.{cfg.task.official_seedset}.json"),
                   **({"delta_best": None} if n.id == "root" else {})}
        orch.executions.revise_measurement(n,reference)
        if n.id == "root":
            orch.executions.document(n,{"state":"complete","phase":"complete","pending":False})
        tree.update(n, score=s, measurement=reference, documentation=orch.executions.read(n)['documentation'],
                    status="incomplete" if cfg.research.enabled and n.id != "root" else "done",
                    metrics={k: v for k, v in m.items() if k not in ("per_seed", "per_item")})
    orch.check_protocol()  # a re-measured baseline lifts a protocol_changed stop
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
    from .setup import waiting_questions
    waiting = waiting_questions(cfg.dir)
    if waiting:
        print(f"WAITING FOR YOU: {len(waiting)} question(s) in {cfg.dir / 'setup' / 'QUESTIONS.md'} "
              f"(answer: rsi setup {cfg.dir} --answer <id>=<choice>)")
        for q in waiting:
            print(f"  [{q['id']}] ({q['importance'] or '?'}) {q['question'][:220]}")
    for n in sorted(tree.nodes.values(), key=lambda n: (n.id != 'root', n.id)):
        print(f"  {n.id:<6} p={n.parent or '-':<5} d={n.depth} {n.status:<10} {n.verdict or '-':<10} {fmt_score(n.score):>10} "
              f"Δp={fmt_score(n.delta_parent):>8} {human_duration(n.duration_s):>7}  {n.title}")
    _print_priorities(cfg)
    return 0


def _print_priorities(cfg, limit=5):
    """This round's phase and the top candidate parents with their priority decomposition."""
    try:
        from .orchestrator import Orchestrator
        orch = Orchestrator(cfg, verbose=False)
        sched = orch.scheduler
        phase = sched.phase()
        top = sched.ranked(phase)[:limit]
    except Exception as e:  # a view; never hides the tree
        print(f"(priority ranking unavailable: {e})")
        return
    waiting = [n.id for n in orch.tree.by_status('waiting')]
    print(f"phase {phase}; top {len(top)} candidate parents by priority"
          + (f"; waiting for results: {', '.join(waiting)}" if waiting else "") + ":")
    for n, p in top:
        print(f"  {n.id:<6} total {p['total']:>6.2f}  exploit {p['exploit']:.2f} explore {p['explore']:.2f} "
              f"info {p['info']:.0f} novelty {p['novelty']:.2f} fail {p['fail']:.2f} explored {p['explored']}  {n.title}")


def cmd_observe(a: argparse.Namespace) -> int:
    """Record a result on the real target (e.g. a leaderboard score) that the study cannot measure itself."""
    from . import proxy
    from .tree import Tree
    cfg = load_experiment(_exp(a.dir))
    if a.node and cfg.tree_path.exists() and a.node not in Tree.load(cfg.tree_path).nodes:
        print(f"unknown node {a.node}")
        return 2
    record = proxy.add_observation(cfg.dir, a.text, node=a.node, metric=a.metric, value=a.value)
    if cfg.tree_path.exists():
        proxy.write(cfg, Tree.load(cfg.tree_path))
    print(f"recorded in {cfg.dir / proxy.OBSERVATIONS}: {json.dumps(record, ensure_ascii=False)}")
    print("the research lead and course corrector read it from their next session on")
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
    i.add_argument("--max-attempts", type=int, default=None, help="total implementation/evaluation attempts, separate from hypotheses")
    i.add_argument("--parallel", type=int, default=2, help="worker concurrency in legacy mode; research loop executes one at a time")
    i.add_argument("--patience", type=int, default=4)
    i.add_argument("--target", type=float, default=None)
    i.add_argument("--max-wallclock", type=int, default=None)
    i.add_argument("--max-gpu-hours", type=float, default=None)
    i.add_argument("--notes", default="")
    i.add_argument("--on-finish", default="", help="shell command run after the final report; {exp_dir} is substituted")
    i.add_argument("--no-narrative", action="store_true")
    i.add_argument("--no-memory", action="store_true", help="disable the research wiki and research scheduling")
    i.add_argument("--memory-dir", help="shared wiki directory (default: experiments/_memory/<task>)")
    i.add_argument("--no-research-loop", action="store_true", help="use the legacy tree scheduler")
    i.add_argument("--research-runner", choices=["grok", "pi", "script"])
    i.add_argument("--research-model", help="default: implementation worker model")
    i.add_argument("--research-effort", help="default: implementation worker effort")
    i.add_argument("--think-timeout", type=int, default=900, help="seconds per full research review")
    i.add_argument("--review-every", type=int, default=5,
                   help="full review after this many experiments (1 = every decision, 0 = only on triggers)")
    i.add_argument("--yolo", action="store_true",
                   help="a human-proxy agent answers routine and mid-run questions; critical first-setup questions still go to you")
    i.add_argument("--calibration-runs", type=int, default=3, help="baseline evaluations measuring run-to-run noise (0 skips)")
    i.add_argument("--no-maintainer", action="store_true", help="use the existing utility for wiki synthesis")
    i.add_argument("--maintainer-runner", choices=["grok", "pi", "script"], default="pi")
    i.add_argument("--maintainer-model", default="openai-codex/gpt-6-luna")
    i.add_argument("--maintainer-effort", default="medium")
    i.add_argument("--force", action="store_true")
    i.set_defaults(fn=cmd_init)

    st = sub.add_parser("setup", help="calibrate noise, review the setup, record decisions (required before a research run)")
    st.add_argument("dir")
    st.add_argument("--answer", action="append", help="id=value answer to a setup question; repeatable")
    st.add_argument("--accept-recommended", action="store_true",
                    help="you accept the reviewer's recommendation for every question waiting for you")
    st.add_argument("--yolo", dest="yolo", action="store_true", default=None,
                    help="let a human-proxy agent answer routine and mid-run questions")
    st.add_argument("--no-yolo", dest="yolo", action="store_false")
    st.add_argument("--quiet", action="store_true")
    st.set_defaults(fn=cmd_setup)

    ob = sub.add_parser("observe", help="record a result on the real target (e.g. a leaderboard score) for the study")
    ob.add_argument("dir")
    ob.add_argument("text", help="what was measured and how, e.g. 'Kaggle public LB of the n007 notebook'")
    ob.add_argument("--node", help="the node whose code produced it")
    ob.add_argument("--metric", help="short metric name, e.g. kaggle_public_lb")
    ob.add_argument("--value", type=float)
    ob.set_defaults(fn=cmd_observe)

    r = sub.add_parser("run", help="run or resume an experiment")
    r.add_argument("dir")
    r.add_argument("--quiet", action="store_true")
    r.set_defaults(fn=cmd_run)

    mem = sub.add_parser("memory", help="manage the shared research wiki without launching experiments")
    mem.add_argument("action", choices=["enable", "disable", "status", "sync", "reflect", "review", "ingest"])
    mem.add_argument("dir")
    mem.add_argument("--path", help="shared wiki base directory, used with enable")
    mem.add_argument("--source", help="local UTF-8 text/Markdown research source, used with ingest")
    mem.add_argument("--label", help="source title/citation")
    mem.add_argument("--batches", type=int, default=1, help="maximum paid reflection calls (1-10)")
    mem.set_defaults(fn=cmd_memory)

    loop = sub.add_parser("research", help="enable, disable or inspect the decide/implement/analyze loop")
    loop.add_argument("action", choices=["enable", "disable", "status", "repair"])
    loop.add_argument("dir")
    for role in ("research", "maintainer"):
        loop.add_argument("--" + role + "-runner", choices=["grok", "pi", "script"])
        loop.add_argument("--" + role + "-model")
        loop.add_argument("--" + role + "-effort")
    loop.add_argument("--review-every", type=int, help="full review after this many experiments; used with enable")
    loop.set_defaults(fn=cmd_research)

    mon = sub.add_parser("monitor", help="inspect task completion and model wake receipts; no model calls")
    mon.add_argument("dir")
    mon.set_defaults(fn=cmd_monitor)

    close = sub.add_parser("closeout", help="finish analysis/handoffs for validated measured nodes; no new experiments")
    close.add_argument("dir")
    close.add_argument("--node", action="append", help="node to recover; repeatable")
    close.add_argument("--seconds", type=int, default=600, help="separate bounded editorial recovery budget")
    close.add_argument("--quiet", action="store_true")
    close.set_defaults(fn=cmd_closeout)

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

    jb = sub.add_parser("job", help="worker side: submit a long command to the task queue; the session is resumed when it ends")
    jb.add_argument("action", choices=["submit"])
    jb.add_argument("--node-dir", required=True, help="this node's notes directory (nodes/<id>), as given in the worker instructions")
    jb.add_argument("--gpus", type=int, default=0)
    jb.add_argument("--timeout", type=int, default=3600, help="seconds before the queue kills the job")
    jb.add_argument("--stall", type=int, default=0, help="kill when --metrics stops growing for this long (0 = off)")
    jb.add_argument("--metrics", help="JSONL progress file the command writes ({step, value} per line)")
    jb.add_argument("--result", help="result file the command writes when it finishes")
    jb.add_argument("--label", help="short description")
    jb.add_argument("cmd", nargs="*", help="the command and its arguments, after a `--` separator (run in the current directory)")
    jb.set_defaults(fn=cmd_job)

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
    c.add_argument("--max-attempts", type=int, help="new total execution-attempt cap")
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

    argv = list(sys.argv[1:] if argv is None else argv)
    command = None
    if argv[:1] == ["job"] and "--" in argv:  # everything after `--` is the job's own command line
        cut = argv.index("--")
        argv, command = argv[:cut], argv[cut + 1:]
    a = p.parse_args(argv)
    if command is not None:
        a.cmd = command
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
