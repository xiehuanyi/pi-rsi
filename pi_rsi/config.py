"""Experiment configuration (rsi.toml) and task-pack configuration (task.toml)."""
from __future__ import annotations

import dataclasses
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RunnerCfg:
    kind: str = "grok"            # grok | pi
    model: str = "grok-4.6"
    effort: str = "high"          # grok reasoning effort / pi thinking level
    max_turns: int = 80
    node_timeout_s: int = 1800    # wall-clock per worker session
    idle_timeout_s: int = 420     # no output for this long -> kill
    extra_args: list[str] = field(default_factory=list)


@dataclass
class UtilityCfg:
    kind: str = "grok"
    model: str = "grok-4.5"
    effort: str = "low"
    timeout_s: int = 600


@dataclass
class SearchCfg:
    width_root: int = 3          # candidates generated at the root (breadth-first layer)
    width: int = 2               # max children per non-root node
    depth: int = 4               # max depth (root = 0)
    max_nodes: int = 12          # total non-root nodes to run (retries included)
    max_parallel: int = 2        # concurrent worker sessions
    patience: int = 4            # consecutive completed nodes without a new global best -> stop
    max_retries: int = 1         # retries per hypothesis after a crash/failed node
    target_score: float | None = None
    max_wallclock_s: int | None = None
    root_eval: bool = True       # evaluate the starter to get the root score


@dataclass
class TaskCfg:
    name: str = ""
    dir: str = ""                # absolute path of the task pack
    brief: str = "TASK.md"
    docs: list[str] = field(default_factory=list)
    starter_dir: str = "starter"
    eval_dir: str = "eval"
    python: str = "python3"      # interpreter used for the evaluator (relative to task dir or absolute)
    eval_command: str = "{python} {task_dir}/eval/eval.py --agent-dir {worktree} --seedset {seedset} --out {out}"
    worker_eval_command: str = "python eval/eval.py --seedset {seedset}"
    worker_val_command: str | None = None   # None -> same command with the official seedset; "" -> hidden (worker cannot run it)
    final_eval_root: bool = True            # also evaluate the baseline on the final seedset for the report
    seedsets: list[str] = field(default_factory=lambda: ["quick", "validation", "test"])
    official_seedset: str = "validation"
    final_seedset: str = "test"
    quick_seedset: str = "quick"
    eval_timeout_s: int = 900
    higher_is_better: bool = True
    score_key: str = "score"
    reference_scores: dict[str, float] = field(default_factory=dict)


@dataclass
class ExperimentCfg:
    name: str
    dir: Path
    task: TaskCfg
    runner: RunnerCfg = field(default_factory=RunnerCfg)
    utility: UtilityCfg = field(default_factory=UtilityCfg)
    search: SearchCfg = field(default_factory=SearchCfg)
    notes: str = ""

    # derived paths -------------------------------------------------------
    @property
    def repo_dir(self) -> Path:
        return self.dir / "repo"

    @property
    def worktrees_dir(self) -> Path:
        return self.dir / "worktrees"

    @property
    def nodes_dir(self) -> Path:
        return self.dir / "nodes"

    @property
    def tree_path(self) -> Path:
        return self.dir / "tree.json"

    @property
    def events_path(self) -> Path:
        return self.dir / "events.jsonl"

    @property
    def insights_path(self) -> Path:
        return self.dir / "INSIGHTS.md"

    @property
    def deadends_path(self) -> Path:
        return self.dir / "DEADENDS.md"

    @property
    def task_dir(self) -> Path:
        return Path(self.task.dir)

    def to_dict(self) -> dict[str, Any]:
        d = {
            "experiment": {"name": self.name, "notes": self.notes},
            "task": dataclasses.asdict(self.task),
            "runner": dataclasses.asdict(self.runner),
            "utility": dataclasses.asdict(self.utility),
            "search": dataclasses.asdict(self.search),
        }
        return d


def _fill(dc_cls, data: dict | None):
    data = dict(data or {})
    names = {f.name for f in dataclasses.fields(dc_cls)}
    unknown = set(data) - names
    if unknown:
        raise ValueError(f"unknown keys for {dc_cls.__name__}: {sorted(unknown)}")
    return dc_cls(**data)


def load_task_cfg(task_dir: Path) -> TaskCfg:
    task_dir = Path(task_dir).resolve()
    with open(task_dir / "task.toml", "rb") as f:
        raw = tomllib.load(f)
    data = dict(raw.get("task", {}))
    data.update(raw.get("eval", {}))
    data["dir"] = str(task_dir)
    data.setdefault("name", task_dir.name)
    return _fill(TaskCfg, data)


def write_experiment_toml(cfg: ExperimentCfg) -> None:
    """Serialize as TOML by hand (stdlib has no writer)."""
    def val(v):
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return repr(v)
        if isinstance(v, str):
            return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
        if isinstance(v, list):
            return "[" + ", ".join(val(x) for x in v) + "]"
        if isinstance(v, dict):
            return "{" + ", ".join(f"{k} = {val(x)}" for k, x in v.items()) + "}"
        raise TypeError(type(v))

    lines = []
    for section, body in cfg.to_dict().items():
        lines.append(f"[{section}]")
        for k, v in body.items():
            if v is None:
                continue
            lines.append(f"{k} = {val(v)}")
        lines.append("")
    (cfg.dir / "rsi.toml").write_text("\n".join(lines), encoding="utf-8")


def load_experiment(exp_dir: Path) -> ExperimentCfg:
    exp_dir = Path(exp_dir).resolve()
    with open(exp_dir / "rsi.toml", "rb") as f:
        raw = tomllib.load(f)
    exp = raw.get("experiment", {})
    task = _fill(TaskCfg, raw.get("task", {}))
    return ExperimentCfg(
        name=exp.get("name", exp_dir.name),
        dir=exp_dir,
        task=task,
        runner=_fill(RunnerCfg, raw.get("runner", {})),
        utility=_fill(UtilityCfg, raw.get("utility", {})),
        search=_fill(SearchCfg, raw.get("search", {})),
        notes=exp.get("notes", ""),
    )
