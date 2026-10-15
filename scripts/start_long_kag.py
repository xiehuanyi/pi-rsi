"""Initialize an isolated, bounded long Kaggriculture search; never submit remotely."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pi_rsi.config import load_experiment, write_experiment_toml
from pi_rsi.memory import ResearchMemory
from pi_rsi.util import atomic_write_json, atomic_write_text, now_iso


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_task(source, target):
    target.mkdir(parents=True)
    for name in ("starter", "eval", "docs"):
        shutil.copytree(source / name, target / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name in ("TASK.md", "task.toml"):
        shutil.copy2(source / name, target / name)
    (target / ".venv").symlink_to((source / ".venv").resolve(), target_is_directory=True)


BRIEF = """# Kaggriculture: long-horizon mechanism research

Improve mean(win + 0.5 * draw) across four frozen archived controllers and both seats.
The starting strategy is the previous pilot's selection-locked n002: repaired V45 plus
late-game deficit-triggered premium front-selling. Its mechanism is a hypothesis, not a proven fact.
Study meaningful market/production/execution mechanisms and retain falsified ideas with their conditions.

## Evaluation
Smoke: 1 seed x 2 seats x 4 opponents = 8 games.
Quick: 8 different seeds x 2 seats x 4 opponents = 64 games. Iterate here.
Selection: 24 different seeds x 2 seats x 4 opponents = 192 games, evaluated by the harness.
The final comparison uses 64 additional seeds, 512 games per locked controller, after search ends.
Those seeds and results are absent from your task. Never locate or read them.
Use outcome as the primary score. Money is diagnostic. Treat each seed across all opponents and seats
as one uncertainty block. Name requested actions as requested, not accepted/executed actions.
This is the same correlated archived pool, not a live-ladder rating or coverage guarantee.

## Research contract
Work only in your worktree, your node notes, the supplied task and explicit memory/context.
Do not read sibling experiments, other campaigns, shared wikis, parent archives or private files.
Do not access the network or submit to Kaggle. Use at most 4 game processes per worker.
agent.py exposes agent(obs). All delivered runtime code must live in agent.py or src/.
Frozen eval/ and docs/ must not change; the archived baseline in docs/ is immutable.
New source modules should each remain below 400 lines. Use only current game observations at runtime.
Do not use evaluation seed lists, opponent identifiers, private labels, replays or future actions.
Each node must state a mechanism question, prediction, falsifier, control commit and factors held fixed.
Make one interpretable intervention. Check its actual diff before calling it a clean ablation.
Report counterexamples, negative outcomes, uncertainty and conditional scope in PROGRESS/HANDOFF.
Do not fill the budget with repeated threshold sweeps. Diagnose failures before proposing another patch.
After an unsuccessful method, explain what new evidence would justify revisiting it.
Keep a conservative control branch that can remove the inherited front-selling overlay if evidence warrants.
"""

TRANSFER = """# Prior pilot: development and selection evidence only

Source: kag-duel-memory-20260913, protocol duel-v1-36c5c68ef38f0622.
The new seed panel makes old scores non-comparable with new scores.
This is a coordinator-curated historical source; conclusions remain conditional.

- Prior root: repaired archived V45, 0.8541667 on 48 selection games.
- Prior n001: low-price sale throttling, 0.75. Did not retain baseline performance on that panel.
- Prior n002: day >= 27 and money behind, front-sell up to two eligible products while protecting
  procurement slots, 0.875. Chosen solely by that selection panel. This is the current code starting point.
- Prior n003: quantity-first AND changed eligibility filters, 0.8333333. Confounded intervention;
  cannot conclude ranking alone caused its outcome.
- Prior n004: cap extra sells to the originally requested tape quantities, 0.8333333. Does not
  distinguish quantity increases, new product insertion and market/procurement interactions.
- All prior parent-change audits were within their estimated noise bands. No mechanism is proved.
- The procurement protection predates this pilot and must not be presented as a new contribution.

Research priorities: fixed-eligibility ranking controls; separate new product insertion from extra units;
identify observed market-price/stock trajectories predicting late-game outcomes; diagnose actual order
execution versus requested orders; investigate conditional production/investment decisions only after
finding a repeatable failure mechanism. Branch into distinct mechanisms, then reproduce promising ones.
No prior confirmation outcomes or current A/B/C campaign results are included in this source.
"""


def main():
    dest = Path(sys.argv[1]).resolve()
    if dest.exists():
        raise SystemExit("destination exists; refusing to overwrite")
    old_dir = ROOT / "experiments/kag-duel-memory-20260913"
    cfg = load_experiment(old_dir)
    lock = json.loads((old_dir / "delivery/LOCK.json").read_text())
    if lock["node"] != "n002":
        raise ValueError("pilot starting candidate differs from the reviewed selection lock")
    winner = old_dir / "worktrees" / lock["node"]
    for relative, expected in lock["files"].items():
        if digest(winner / relative) != expected:
            raise ValueError(f"pilot locked file changed: {relative}")
    dest.mkdir(parents=True)
    task = dest / "task"
    private = dest / "private/confirmation-task"
    for target in (task, private):
        copy_task(cfg.task_dir, target)
        shutil.rmtree(target / "starter")
        (target / "starter/src").mkdir(parents=True)
        for relative in lock["files"]:
            p = Path(relative)
            if p.parts[0] in ("agent.py", "src"):
                out = target / "starter" / p
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(winner / p, out)
        atomic_write_text(target / "TASK.md", BRIEF)
    base = json.loads((task / "eval/protocol.json").read_text())
    # Earlier pilot seeds are <10k, and both existing memory-study repetitions
    # were sampled below 1m. This disjoint range avoids reading their holdouts.
    seeds = random.SystemRandom().sample(range(2000000, 100000000), 97)
    panels = {"smoke": seeds[:1], "quick": seeds[1:9], "validation": seeds[9:33]}
    for target, groups, role in ((task, panels, "long_search_only"),
                                 (private, {"confirmation": seeds[33:]}, "locked_candidate_confirmation")):
        proto = copy.deepcopy(base)
        proto.pop("id", None)
        for source in proto["sources"].values():
            source.pop("path", None)
        proto.update(seeds=groups, role=role,
                     baseline="pilot selection-locked n002; previous outcome mechanism remains tentative")
        proto["id"] = "kag-long-" + hashlib.sha256(json.dumps(proto, sort_keys=True).encode()).hexdigest()[:16]
        atomic_write_json(target / "eval/protocol.json", proto)
    os.chmod(dest / "private", 0o700)
    # Private evaluation can use more CPU after search has drained.
    private_toml = (private / "task.toml").read_text().replace("--workers 4", "--workers 8")
    atomic_write_text(private / "task.toml", private_toml)
    cfg.name, cfg.dir = dest.name, dest
    cfg.task.name, cfg.task.dir = "kaggriculture-long-v1", str(task)
    cfg.task.seedsets = ["smoke", "quick", "validation"]
    cfg.task.final_seedset = ""
    cfg.task.eval_timeout_s = 1500
    cfg.runner.model, cfg.runner.effort = "grok-4.6", "high"
    cfg.runner.max_turns, cfg.runner.node_timeout_s, cfg.runner.idle_timeout_s = 120, 2400, 420
    cfg.search.width_root, cfg.search.width, cfg.search.depth = 6, 3, 12
    cfg.search.max_nodes, cfg.search.max_parallel = 96, 2
    cfg.search.patience, cfg.search.max_wallclock_s = 96, 86400
    cfg.memory.path = str(dest / "wiki")
    cfg.memory.protocol_id = json.loads((task / "eval/protocol.json").read_text())["id"]
    cfg.memory.reflect_every, cfg.memory.batch_size = 3, 8
    cfg.memory.context_chars, cfg.memory.research_every, cfg.memory.patience_grace = 18000, 3, 0
    cfg.hooks.on_finish, cfg.hooks.narrative, cfg.ops.auto = "", False, False
    cfg.notes = "24h / 96-node research from pilot n002; new seeds; separate wiki and private confirmation."
    write_experiment_toml(cfg)
    atomic_write_text(dest / "TRANSFER.md", TRANSFER)
    shutil.copy2(old_dir / "CONTROL_REVIEW.md", dest / "CONTROL_REVIEW.md")
    atomic_write_text(dest / "HUMAN.md", TRANSFER + "\n" +
                      "Use the longer node budget for diagnostics, controlled methods and replication. "
                      "Do not read any other campaign or confirmation directory.\n")
    memory = ResearchMemory(cfg)
    for name in ("TRANSFER.md", "CONTROL_REVIEW.md"):
        memory.ingest(dest / name, "Historical development evidence: " + name)
    harness = dest / "harness"
    shutil.copytree(ROOT / "pi_rsi", harness / "pi_rsi",
                    ignore=shutil.ignore_patterns("tasks", "__pycache__", "*.pyc"))
    (harness / "scripts").mkdir()
    for name in ("duel_delivery.py", "long_kag_driver.py"):
        shutil.copy2(ROOT / "scripts" / name, harness / "scripts" / name)
    fingerprints = {}
    for folder in (task, private, harness):
        for p in sorted(folder.rglob("*")):
            if p.is_file() and not p.is_symlink() and "__pycache__" not in p.parts:
                fingerprints[str(p.relative_to(dest))] = digest(p)
    fingerprints["rsi.toml"] = digest(dest / "rsi.toml")
    atomic_write_json(dest / "PLAN.json", {
        "created_at": now_iso(), "starting_node": lock["node"], "starting_commit": lock["commit"],
        "scheduling_seconds": 86400, "max_nodes": 96, "parallel_workers": 2,
        "node_seconds": 2400, "drain_seconds": 7200, "confirmation_games_per_controller": 512,
        "files": fingerprints, "wiki": str(memory.root), "submitted": False})
    atomic_write_text(dest / "PROTOCOL.md", """# Kaggriculture 长预算研究

调度预算 24 小时，最多 96 个非根节点（包含重试），两路并行。
每个初始 worker 最长 40 分钟、120 轮；已派发工作、交接、评测和整理允许随后收尾。
外层看守保留首次启动时间，24 小时停止派发，最多再允许 2 小时收尾。
模型：实验 Grok 4.6 high；规划、整理与审计 Grok 4.5 low。

继承上一轮选择集锁定的 n002。新 smoke/quick/selection 分别 1/8/24 个互不重叠种子，
双方座位、同一四对手池。正式选择 192 场/策略。历史分数不能与新分数直接比较。
独立 wiki 导入以前的开发证据与控制审查；不导入旧确认结果或正在运行的 A/B/C 结果。
每第三次扩展优先机制区分实验。记录预测、反证、控制因素、失败条件和方法修订。

冻结任务与框架副本。搜索完成后锁定单个选择集最优候选及其源码哈希，
使用私有 64 个新种子，512 场/策略，对比最终候选与本轮起点 n002。
确认不写入研究 wiki，不用于重选或修改候选。若起点仍最优，报告无新增收益。
报告按种子块配对的平均差、双侧精确符号翻转检验；用整数格点动态计数保持精确性。
局部支持条件：平均增益为正、p ≤ 0.05、各对手汇总无回退、候选无执行错误。
同一相关归档池的确认不代表线上榜单泛化。最终保留提交包和官方环境自对弈检查。
不会自动提交 Kaggle。观察网页只暴露结果文件，不暴露私有确认集。
""")
    print(json.dumps({"experiment": str(dest), "wiki": str(memory.root), "frozen_files": len(fingerprints)}, indent=2))


if __name__ == "__main__":
    main()
