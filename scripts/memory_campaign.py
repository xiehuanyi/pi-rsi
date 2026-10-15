#!/usr/bin/env python3
"""Frozen, replicated Kaggriculture memory comparison; no external submission.

init freezes code, task packs, equal resource ceilings, and a private confirmation
panel. run executes two balanced waves, locks ALL winners before confirmation,
then writes descriptive comparisons and arm-masked research-review materials.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import signal
import statistics
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pi_rsi.config import load_experiment, write_experiment_toml
from pi_rsi.util import atomic_write_json, atomic_write_text, now_iso, read_json

ARMS = {"A": "original handoffs and insights; wiki disabled",
        "B": "structured wiki, reflection and stale-proposal review; original best-first scheduling",
        "C": "B plus a discriminating-research preference every third expansion"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest_tree(path):
    return {str(p.relative_to(path)): sha(p) for p in sorted(path.rglob("*"))
            if p.is_file() and not p.is_symlink() and "__pycache__" not in p.parts
            and ".venv" not in p.parts and p.suffix != ".pyc"}


def tokens(costs):
    return sum(int(v.get("input_tokens", 0)) + int(v.get("output_tokens", 0)) for v in costs.values())


def seeded_panels(old_seeds, rng_seed=2026091302):
    rng = random.Random(rng_seed)
    values = rng.sample([n for n in range(10000, 1000000) if n not in set(old_seeds)], 82)
    return {"r1": {"smoke": values[:1], "quick": values[1:5], "validation": values[5:17], "confirmation": []},
            "r2": {"smoke": values[17:18], "quick": values[18:22], "validation": values[22:34], "confirmation": []},
            "confirmation": values[34:82]}


def protocol_with_seeds(base, seeds, role):
    result = copy.deepcopy(base)
    result.pop("id", None)
    result["seeds"] = seeds
    result["role"] = role
    # Preserve hashes/provenance, but do not advertise paths to other experiments.
    for source in result.get("sources", {}).values():
        source.pop("path", None)
    result["id"] = "memory-study-" + hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:16]
    return result


def copy_task(source, dest):
    dest.mkdir(parents=True)
    for name in ("starter", "docs", "eval"):
        shutil.copytree(source / name, dest / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name in ("TASK.md", "task.toml"):
        shutil.copy2(source / name, dest / name)
    (dest / ".venv").symlink_to((source / ".venv").resolve(), target_is_directory=True)


def initialize(dest, template):
    if dest.exists():
        raise ValueError("campaign directory already exists; refusing to overwrite")
    cfg0 = load_experiment(template)
    source = cfg0.task_dir
    old = read_json(source / "eval/protocol.json")
    panels = seeded_panels([s for group in old["seeds"].values() for s in group])
    dest.mkdir(parents=True)
    harness = dest / "harness"
    shutil.copytree(ROOT / "pi_rsi", harness / "pi_rsi",
                    ignore=shutil.ignore_patterns("tasks", "__pycache__", "*.pyc"))
    (harness / "scripts").mkdir()
    shutil.copy2(Path(__file__), harness / "scripts/memory_campaign.py")
    task_dirs = {}
    for rep in ("r1", "r2"):
        task = dest / "tasks" / rep
        copy_task(source, task)
        proto = protocol_with_seeds(old, panels[rep], "search_only")
        atomic_write_json(task / "eval/protocol.json", proto)
        brief = (source / "TASK.md").read_text()
        brief = brief.replace("quick: 2 seeds x 2 seats x 4 opponents = 16 games.",
                              "quick: 4 seeds x 2 seats x 4 opponents = 32 games.")
        brief = brief.replace("validation: 6 different seeds x 2 seats x 4 opponents = 48 games,",
                              "validation: 12 different seeds x 2 seats x 4 opponents = 96 games,")
        # Give all arms exactly the same prior information; no previous pilot winner.
        brief += "\n## Experiment isolation\nWork only in this run's worktree and node notes, the supplied task files, " \
                 "and the explicitly supplied context. Do not inspect other runs, prior campaign artifacts, " \
                 "parent-directory archives, private confirmation files or shared research wikis. " \
                 "Do not access the network. Confirmation is absent from this task pack. " \
                 "Use at most four game processes at once. Keep all code edits inside the worktree.\n" \
                 "For each proposed experiment, state its mechanism question, prediction, falsifier, " \
                 "and the factors held fixed. In the handoff separate observations from causal explanations; " \
                 "record counterexamples, failed attempts and limitations.\n"
        atomic_write_text(task / "TASK.md", brief)
        task_dirs[rep] = task
    private = dest / "private" / "confirmation-task"
    copy_task(source, private)
    atomic_write_json(private / "eval/protocol.json", protocol_with_seeds(old,
                      {"smoke": [], "quick": [], "validation": [], "confirmation": panels["confirmation"]},
                      "locked_all_runs_confirmation"))
    runs = []
    for rep in ("r1", "r2"):
        for arm in ARMS:
            cfg = copy.deepcopy(cfg0)
            cfg.name = f"memory-{arm}-{rep}"
            cfg.dir = dest / "runs" / cfg.name
            cfg.dir.mkdir(parents=True)
            cfg.task.dir = str(task_dirs[rep])
            cfg.task.name = "kaggriculture-memory-study"
            cfg.task.seedsets = ["smoke", "quick", "validation"]
            cfg.task.final_seedset = ""
            cfg.runner.node_timeout_s = 1200
            cfg.runner.idle_timeout_s = 300
            cfg.runner.max_turns = 80
            cfg.search.width_root = 4
            cfg.search.width = 3
            cfg.search.depth = 6
            cfg.search.max_nodes = 24
            cfg.search.max_parallel = 1
            cfg.search.patience = 24
            cfg.search.max_wallclock_s = 21600
            cfg.search.max_retries = 1
            cfg.memory.enabled = arm != "A"
            cfg.memory.path = str(dest / "wikis" / cfg.name)
            cfg.memory.protocol_id = read_json(task_dirs[rep] / "eval/protocol.json")["id"]
            cfg.memory.reflect_every = 3
            cfg.memory.batch_size = 8
            cfg.memory.research_every = 3 if arm == "C" else 0
            cfg.memory.patience_grace = 0
            cfg.hooks.narrative = False
            cfg.hooks.on_finish = ""
            cfg.ops.auto = False
            cfg.notes = "Fresh isolated research replication; one intervention per node; no cross-run evidence."
            write_experiment_toml(cfg)
            runs.append({"name": cfg.name, "arm": arm, "rep": rep, "path": str(cfg.dir)})
    plan = {"created_at": now_iso(), "arms": ARMS, "runs": runs, "harness": str(harness),
            "max_nodes_per_run": 24, "scheduling_seconds_per_run": 21600,
            "reported_token_stop_per_run": 6000000, "drain_seconds": 4500,
            "parallel_runs": 3, "private_task": str(private),
            "confirmation_games_per_controller": 384,
            "harness_files": digest_tree(harness),
            "task_files": digest_tree(dest / "tasks"),
            "private_files": digest_tree(dest / "private"),
            "configs": {r["name"]: sha(Path(r["path"]) / "rsi.toml") for r in runs}}
    atomic_write_json(dest / "PLAN.json", plan)
    atomic_write_text(dest / "PROTOCOL.md", protocol_text(plan))
    refresh(dest, plan)
    return plan


def protocol_text(plan):
    return """# Kaggriculture 研究记忆验证 · 预注册方案

三组、每组两次独立搜索；模型为 Grok 4.6 high，整理/审计模型为 Grok 4.5 low。
A 保留原有交接与 insights/deadends；B 加结构化记忆、反思、旧提案重审；
C 在 B 上增加每第三次扩展优先机制区分实验。B 并非只增加存储：反思与重规划也是处理的一部分。

每次最多 24 个非根节点（含重试）、6 小时调度时间，单 worker、每节点 20 分钟。
另设已报告输入+输出 token 合计 600 万的停止阈值，包含 worker、planner、反思、审计和补救。
达到阈值停止派发，已在运行的节点允许收尾；不是精确 token 硬上限，可能超出一个节点及同期整理调用。
超时/缺失 usage 的调用可能少报 token，实际次数、时长、usage 缺失和成本须一并报告。
六次总计最多 144 个实验、36 小时调度预算；三次并行、两波。收尾与最后评测另计。
这是相同资源上限下的部署效果比较，不冒充严格相同实际 token/计算量的因果实验。

同一重复内三组使用相同起点和搜索种子。两次重复使用不同搜索种子。
每次 quick 4 种子×双方座位×4 对手=32场；validation 12 种子=96场。
每个 wiki 从空库开始，互不共享。不给任一组导入上一轮结果或最优策略。
所有组收到同样的任务要求和已有基线说明。禁止访问其他运行；这是提示词隔离，
不是文件系统沙箱；最终须审计访问日志是否跨组读取。冻结 harness 副本，避免其他任务的代码改动干扰。

全部搜索结束后，先同时锁定每次在选择集上最好的一个候选（包括基线），再评测。
确认集为新的48个种子×双方座位×4对手=384场/策略；六个候选共享同一确认面板。
确认种子和结果不进入任务包、worker上下文、wiki或后续选择。不得用确认分数挑选或修改候选。
保留四个旧对手用于控制变量；本实验不验证真实天梯泛化，不自动提交 Kaggle。

主要比较：每次搜索的锁定策略的确认胜平分，报告 C−A、B−A、C−B 在两次重复的差值与均值。
独立研究运行才是记忆效果的重复单位，384场对局不是384次独立的记忆系统实验。
只有两次重复，统计功效有限；不以种子级显著性声称记忆系统普遍有效。
同时保留节点数、耗时与累计已报告token的搜索轨迹，不只挑最好的一次运行展示。

科研质量评审：所有节点统一提取问题、假设、预测、反证标准、实际代码差异、正式结果、交接；
打乱并隐藏组名，按以下维度0/1/2打分：
1. 重复：无理由重复失败 / 有边界说明的复查 / 有新证据或有效机制区分；
2. 消融：多因素混杂 / 控制不完全 / 固定其他因素并可解释干预；
3. 修订：忽略反证 / 记录但未更新 / 修改结论范围或下一步；
4. 证据链：只有故事 / 部分来源 / motivation→method→预测→结果可核查。
这些需要基于日志和代码的人工审核。系统只生成评审包，不自动给自己科研质量打分。
遮盖组名不能完全隐藏记忆处理的文字特征，因此属于尽可能盲化，而非保证双盲。

确认结果、资源曲线与评审包自动生成；最终结论在评审完成前标记为待验证。
任何运行失败都保留并报告，不用成功运行替换失败重复。
"""


def run_summary(run):
    path = Path(run["path"])
    tree = read_json(path / "tree.json", {})
    nodes = tree.get("nodes", [])
    done = [n for n in nodes if n.get("status") == "done" and n["id"] != "root"]
    best = next((n for n in nodes if n["id"] == tree.get("best")), {})
    costs = read_json(path / "costs.json", {})
    return {**run, "state": read_json(path / "campaign-run.json", {"status": "queued"}),
            "completed": len(done), "failed": sum(n.get("status") == "failed" for n in nodes),
            "best_node": best.get("id"), "selection_score": best.get("score"),
            "reported_tokens": tokens(costs), "costs": costs}


def refresh(dest, plan):
    runs = [run_summary(r) for r in plan["runs"]]
    status = {"updated_at": now_iso(), "runs": runs,
              "result_ready": (dest / "RESULTS.md").exists()}
    atomic_write_json(dest / "STATUS.json", status)
    lines = ["# 记忆系统验证进度", "", f"更新：{status['updated_at']}", "",
             "| 运行 | 状态 | 完成节点 | 失败节点 | 最好选择分 | 已报告token |",
             "|---|---|---:|---:|---:|---:|"]
    for r in runs:
        lines.append(f"| {r['name']} | {r['state']['status']} | {r['completed']} | {r['failed']} | "
                     f"{r['selection_score']} | {r['reported_tokens']:,} |")
    lines += ["", "选择分不能代表记忆收益。全部结束后锁定候选、统一跑新种子，并审查科研质量。",
              "", "[实验方案](PROTOCOL.md) · [结果](RESULTS.md)"]
    atomic_write_text(dest / "STATUS.md", "\n".join(lines) + "\n")
    return status


def verify_frozen(dest, plan):
    for root, expected in ((Path(plan["harness"]), plan["harness_files"]),
                           (dest / "tasks", plan["task_files"]), (dest / "private", plan["private_files"])):
        current = digest_tree(root)
        if current != expected:
            changed = sorted(k for k in set(current) | set(expected) if current.get(k) != expected.get(k))
            raise ValueError(f"frozen files changed: {root}: {changed[:10]}")
    for r in plan["runs"]:
        if sha(Path(r["path"]) / "rsi.toml") != plan["configs"][r["name"]]:
            raise ValueError(f"run configuration changed: {r['name']}")


def kill_descendants(pid):
    rows = subprocess.check_output(["ps", "-eo", "pid=,ppid="], text=True)
    pairs = [tuple(map(int, line.split())) for line in rows.splitlines()]
    targets = {pid}
    while True:
        more = {p for p, parent in pairs if parent in targets}
        if more <= targets:
            break
        targets |= more
    for p in targets:
        try:
            os.kill(p, signal.SIGKILL)
        except ProcessLookupError:
            pass


def run_one(run, plan):
    path = Path(run["path"])
    status_path = path / "campaign-run.json"
    previous = read_json(status_path)
    if previous:
        if previous["status"] in ("finished", "failed"):
            return previous
        # Do not silently reset the wallclock or overlap a surviving worker.
        raise RuntimeError(f"interrupted campaign needs inspection before resuming {run['name']}")
    start = time.monotonic()
    state = {"status": "running", "started_at": now_iso(), "stop_request": None}
    with (path / "coordinator.log").open("w") as log:
        proc = subprocess.Popen([sys.executable, "-m", "pi_rsi.cli", "run", str(path)],
                                cwd=plan["harness"], stdout=log, stderr=subprocess.STDOUT,
                                env={**os.environ, "PYTHONUNBUFFERED": "1", "OMP_NUM_THREADS": "1",
                                     "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"})
        state["pid"] = proc.pid
        atomic_write_json(status_path, state)
        while proc.poll() is None:
            elapsed = time.monotonic() - start
            cost = read_json(path / "costs.json", {})
            if not state["stop_request"]:
                reason = "reported_token_budget" if tokens(cost) >= plan["reported_token_stop_per_run"] else (
                         "wallclock_budget" if elapsed >= plan["scheduling_seconds_per_run"] else None)
                if reason:
                    proc.send_signal(signal.SIGTERM)
                    state["stop_request"] = reason
                    state["stop_requested_elapsed_s"] = elapsed
            drain_start = state.get("stop_requested_elapsed_s", plan["scheduling_seconds_per_run"])
            if elapsed > drain_start + plan["drain_seconds"]:
                state["hard_timeout"] = True
                kill_descendants(proc.pid)
                proc.wait()
                break
            state.update(heartbeat=now_iso(), elapsed_s=round(elapsed, 1), reported_tokens=tokens(cost))
            atomic_write_json(status_path, state)
            time.sleep(10)
        actual = read_json(path / "state.json", {})
        state.update(status="finished" if proc.returncode == 0 and actual.get("status") == "finished" else "failed",
                     exit_code=proc.returncode, finished_at=now_iso(), elapsed_s=round(time.monotonic() - start, 1),
                     harness_stop_reason=actual.get("stop_reason"))
        atomic_write_json(status_path, state)
    return state


def source_identity(path):
    # Every tracked candidate file, including config/assets, is locked and copied.
    files = subprocess.check_output(["git", "ls-files", "-z"], cwd=path).decode().split("\0")
    result = {}
    for name in filter(None, files):
        p = path / name
        if p.is_symlink() or not p.resolve().is_relative_to(path.resolve()):
            raise ValueError(f"candidate contains external link: {p}")
        result[name] = sha(p)
    return result


def lock_candidates(dest, plan):
    locks = []
    for run in plan["runs"]:
        path = Path(run["path"])
        if read_json(path / "campaign-run.json", {}).get("status") != "finished":
            raise ValueError("all six runs must finish successfully before confirmatory comparisons")
        tree = read_json(path / "tree.json")
        if any(n["status"] in ("planned", "running", "evaluating") for n in tree["nodes"]):
            raise ValueError("cannot lock an active search")
        winner = next(n for n in tree["nodes"] if n["id"] == tree["best"])
        source = path / "repo" if winner["id"] == "root" else path / "worktrees" / winner["id"]
        if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=source).strip():
            raise ValueError(f"uncommitted tracked changes in {source}")
        files = source_identity(source)
        candidate = dest / "locked" / run["name"]
        candidate.mkdir(parents=True, exist_ok=True)
        for name in files:
            target = candidate / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / name, target)
        locks.append({**run, "node": winner["id"], "commit": winner["commit"],
                      "selection_score": winner["score"], "source": str(source), "candidate": str(candidate),
                      "files": files})
    lock = {"locked_at": now_iso(), "candidates": locks,
            "confirmation_protocol_sha256": sha(Path(plan["private_task"]) / "eval/protocol.json")}
    old = read_json(dest / "LOCK.json")
    if old:
        if old["candidates"] != lock["candidates"] or old["confirmation_protocol_sha256"] != lock["confirmation_protocol_sha256"]:
            raise ValueError("confirmation lock changed; refusing reuse")
        return old
    atomic_write_json(dest / "LOCK.json", lock)
    return lock


def confirm(dest, plan, lock):
    task = Path(plan["private_task"])
    output = dest / "confirmation"
    output.mkdir(exist_ok=True)
    baseline = Path(plan["runs"][0]["path"]) / "repo"
    entries = [("baseline", baseline)] + [(r["name"], Path(r["candidate"])) for r in lock["candidates"]]
    for name, candidate in entries:
        metric_path = output / f"{name}.json"
        if not metric_path.exists():
            with (output / f"{name}.log").open("w") as log:
                subprocess.run([str(task / ".venv/bin/python"), str(task / "eval/eval.py"),
                                "--agent-dir", str(candidate), "--seedset", "confirmation", "--out", str(metric_path),
                                "--workers", "8", "--quiet"], stdout=log, stderr=subprocess.STDOUT,
                               check=True, timeout=1250)
        m = read_json(metric_path)
        if not isinstance(m.get("score"), (int, float)) or m.get("n_games") != 384:
            raise ValueError(f"invalid confirmation: {name}")
    for r in lock["candidates"]:
        if any(sha(Path(r["candidate"]) / p) != value for p, value in r["files"].items()):
            raise ValueError("candidate mutated during confirmation")


def review_pack(dest, plan):
    packets = []
    histories = []
    for run in plan["runs"]:
        path = Path(run["path"])
        tree = read_json(path / "tree.json", {})
        history = {"run": run["name"], "nodes": [], "memory_revisions": []}
        for n in tree.get("nodes", []):
            if n["id"] == "root":
                continue
            nd = path / "nodes" / n["id"]
            notes = {name: (nd / name).read_text() if (nd / name).exists() else ""
                     for name in ("HYPOTHESIS.md", "HANDOFF.md", "PROGRESS.md", "SUMMARY.md", "FAILURE.md")}
            diff = ""
            if n.get("commit") and n.get("base_commit"):
                diff = subprocess.check_output(["git", "diff", n["base_commit"], n["commit"], "--", "agent.py", "src"],
                                                cwd=path / "repo", text=True)
            packet = {"run": run["name"], "node": n["id"], "parent": n.get("parent"),
                            "title": n["title"], "notes": notes,
                            "diff": diff, "status": n["status"], "score": n.get("score"),
                            "metrics": read_json(nd / "eval/metrics.validation.json", {})}
            packets.append(packet)
            history["nodes"].append(copy.deepcopy(packet))
        for revision in sorted((dest / "wikis" / run["name"]).glob("protocols/*/revisions/*/state.json")):
            history["memory_revisions"].append(read_json(revision))
        histories.append(history)
    random.Random(2026091303).shuffle(packets)
    out = dest / "review"
    out.mkdir(exist_ok=True)
    key, rows = {}, []
    for i, p in enumerate(packets, 1):
        label = f"case-{i:03d}"
        key[label] = {"run": p.pop("run"), "node": p.pop("node")}
        text = json.dumps(p, ensure_ascii=False, indent=2)
        for run in plan["runs"]:
            text = text.replace(run["path"], "<run>").replace(run["name"], "<run>")
        text = text.replace(str(dest), "<campaign>")
        atomic_write_text(out / f"{label}.json", text + "\n")
        rows.append(f"{label},,,,,")
    atomic_write_json(dest / "private/review-key.json", key)
    random.Random(2026091304).shuffle(histories)
    history_key = {}
    for i, history in enumerate(histories, 1):
        label = f"history-{i:02d}"
        history_key[label] = history["run"]
        text = json.dumps(history, ensure_ascii=False, indent=2)
        for run in plan["runs"]:
            text = text.replace(run["path"], "<run>").replace(run["name"], "<run>")
        atomic_write_text(out / f"{label}.json", text.replace(str(dest), "<campaign>") + "\n")
    atomic_write_json(dest / "private/history-key.json", history_key)
    atomic_write_text(out / "scores.csv", "case,repeat_quality,ablation_control,counterevidence_revision,evidence_chain,reviewer_notes\n" + "\n".join(rows) + "\n")
    atomic_write_text(out / "README.md", "# 科研质量评审\n\n按 PROTOCOL.md 的四项0/1/2标准逐项核对代码、证据和后续决策。\n"
                      "组名已遮盖并打乱顺序，内容可能仍暴露处理类型。留空即未审核，不视作0分。\n"
                      "history-*.json保留父子关系、完整节点序列与记忆修订，先逐节点评分，再检查后续决策是否响应新证据。\n"
                      "不能只依赖单节点包断言减少重复或改善长期记忆。还须检查原始runner日志的文件访问，排查跨组读取。\n")


def summarize(dest, plan):
    rows = []
    for r in plan["runs"]:
        s = run_summary(r)
        m = read_json(dest / "confirmation" / f"{r['name']}.json")
        rows.append({**s, "confirmation_score": m["score"], "wins": m["wins"], "draws": m["draws"],
                     "losses": m["losses"], "errors": m["errors"], "per_opponent": m["per_opponent"]})
    comparisons = {}
    for left, right in (("C", "A"), ("B", "A"), ("C", "B")):
        deltas = [next(r["confirmation_score"] for r in rows if r["arm"] == left and r["rep"] == rep) -
                  next(r["confirmation_score"] for r in rows if r["arm"] == right and r["rep"] == rep)
                  for rep in ("r1", "r2")]
        comparisons[f"{left}-{right}"] = {"replicate_deltas": deltas, "mean_delta": statistics.mean(deltas)}
    atomic_write_json(dest / "RESULTS.json", {"runs": rows, "comparisons": comparisons,
                      "memory_effect_decision": "exploratory_pending_research_review", "replications_per_arm": 2})
    lines = ["# Kaggriculture 记忆系统验证结果", "", "两次独立搜索/组；以下为描述性比较，科研质量评审尚待完成。", "",
             "| 运行 | 完成/失败节点 | 选择分 | 确认分 | 胜/平/负 | 报告token |",
             "|---|---:|---:|---:|---|---:|"]
    for r in rows:
        lines.append(f"| {r['name']} | {r['completed']}/{r['failed']} | {r['selection_score']:.3%} | "
                     f"{r['confirmation_score']:.3%} | {r['wins']}/{r['draws']}/{r['losses']} | {r['reported_tokens']:,} |")
    for name, c in comparisons.items():
        lines.append(f"\n{name}：两次差值 {c['replicate_deltas']}；平均 {c['mean_delta']:+.3%}。")
    lines += ["", "不能将种子/对局当作独立记忆系统重复。相同资源上限不等于相同实际token。",
              "当前四对手池不代表线上天梯。没有提交 Kaggle。",
              "", "[科研质量评审包](review/README.md) · [预注册方案](PROTOCOL.md) · [资源轨迹](TRAJECTORIES.json)"]
    atomic_write_text(dest / "RESULTS.md", "\n".join(lines) + "\n")


def trajectories(dest, plan):
    result = {}
    for run in plan["runs"]:
        p = Path(run["path"])
        tree = read_json(p / "tree.json", {})
        result[run["name"]] = {"nodes": [{k: n.get(k) for k in ("id", "parent", "status", "score", "created_at", "finished_at", "duration_s")}
                                                 for n in tree.get("nodes", [])],
                                "costs": read_json(p / "costs.json", {}),
                                "events": [json.loads(line) for line in (p / "events.jsonl").read_text().splitlines()
                                           if line.strip()] if (p / "events.jsonl").exists() else []}
    atomic_write_json(dest / "TRAJECTORIES.json", result)


def execute(dest):
    plan = read_json(dest / "PLAN.json")
    with (dest / ".driver.lock").open("w") as lockfile:
        fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
        verify_frozen(dest, plan)
        try:
            for rep in ("r1", "r2"):
                wave = [r for r in plan["runs"] if r["rep"] == rep]
                random.Random(20260913 + int(rep[-1])).shuffle(wave)
                with ThreadPoolExecutor(max_workers=3) as pool:
                    futures = [pool.submit(run_one, r, plan) for r in wave]
                    while not all(f.done() for f in futures):
                        refresh(dest, plan)
                        time.sleep(10)
                    results = [f.result() for f in futures]
                refresh(dest, plan)
                if any(r["status"] != "finished" for r in results):
                    raise RuntimeError("a balanced wave failed; inspect before spending the next wave's budget")
            verify_frozen(dest, plan)
            lock = lock_candidates(dest, plan)
            confirm(dest, plan, lock)
            trajectories(dest, plan)
            review_pack(dest, plan)
            summarize(dest, plan)
            atomic_write_json(dest / "COMPLETED.json", {"at": now_iso(), "status": "awaiting_research_quality_review"})
        except Exception:
            atomic_write_json(dest / "FAILED.json", {"at": now_iso(), "error": traceback.format_exc()})
            trajectories(dest, plan)
            raise
        finally:
            refresh(dest, plan)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["init", "run", "status"])
    ap.add_argument("campaign", type=Path)
    ap.add_argument("--template", type=Path)
    a = ap.parse_args()
    dest = a.campaign.resolve()
    if a.action == "init":
        if not a.template:
            ap.error("init requires --template")
        plan = initialize(dest, a.template)
        print(json.dumps({"campaign": str(dest), "runs": len(plan["runs"]), "max_nodes": 144}))
    elif a.action == "run":
        execute(dest)
    else:
        print(json.dumps(refresh(dest, read_json(dest / "PLAN.json")), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
