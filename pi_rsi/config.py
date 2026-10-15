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
class MaintainerCfg:
    enabled: bool = True
    kind: str = "pi"
    model: str = "openai-codex/gpt-6-luna"
    effort: str = "medium"
    timeout_s: int = 600


@dataclass
class ResearchCfg:
    enabled: bool = True
    kind: str = ""               # inherit the research worker's runtime/model, not the cheap utility
    model: str = ""
    effort: str = ""             # inherit worker reasoning effort
    max_turns: int = 30
    timeout_s: int = 900
    idle_timeout_s: int = 420
    analysis_timeout_s: int = 600
    candidates: int = 3
    max_tuning_trials: int = 6
    max_stage_retries: int = 1  # document-stage retries; independent of implementation attempts
    context_chars: int = 40000  # bounded snapshot digest in a full review; the full snapshot stays on disk
    review_every: int = 5       # full review after this many experiments; 1 = every decision, 0 = only on triggers
    measure_active: bool = True  # a component the worker switched off is officially measured switched on
    skip_unmeasured: bool = True  # a node declaring no new component gets no official evaluation

    def __post_init__(self):
        if not 2 <= self.candidates <= 6:
            raise ValueError("research candidates must be between 2 and 6")
        if self.review_every < 0:
            raise ValueError("research review_every cannot be negative")
        if self.context_chars < 8000:
            raise ValueError("research context_chars must be at least 8000")
        if min(self.max_turns, self.timeout_s, self.idle_timeout_s,
               self.analysis_timeout_s, self.max_tuning_trials) < 1:
            raise ValueError("research budgets must be positive")
        if self.max_stage_retries < 0:
            raise ValueError("documentation retries cannot be negative")


@dataclass
class SetupCfg:
    enabled: bool = True          # research-mode runs start only after a confirmed setup (rsi setup)
    proxy: bool = False           # yolo: a human-proxy agent answers routine and mid-run questions
    calibration_runs: int = 3     # baseline evaluations (incl. root) measuring run-to-run noise; 0 skips
    course_k: int = 0             # course correction after K experiments without real progress; 0 = search.patience

    def __post_init__(self):
        if self.calibration_runs < 0 or self.course_k < 0:
            raise ValueError("setup calibration_runs and course_k cannot be negative")


@dataclass
class OpsCfg:
    kind: str = ""               # defaults to the worker runner
    model: str = ""
    effort: str = ""
    auto: bool = True            # call the ops agent after repeated evaluator failures
    max_turns: int = 40
    timeout_s: int = 1500


@dataclass
class HooksCfg:
    on_finish: str = ""          # shell command run after the final report (e.g. publish to the blog); {exp_dir} is substituted
    narrative: bool = True       # writer pass at the end (NARRATIVE.md)
    narrative_language: str = "Chinese"
    max_submissions: int = 3     # cap on final-level evaluations (e.g. Kaggle submissions) per experiment


@dataclass
class SearchCfg:
    width_root: int = 3          # candidates generated at the root (breadth-first layer)
    width: int = 2               # max children per non-root node
    depth: int = 4               # max depth (root = 0)
    max_nodes: int = 12          # distinct hypotheses; execution retries never allocate hypotheses
    max_attempts: int | None = None  # total execution cap; default max_nodes * (max_retries + 1)
    max_parallel: int = 2        # concurrent worker sessions
    patience: int = 4            # consecutive completed nodes without a new global best -> stop
    max_retries: int = 1         # retries per hypothesis after a crash/failed node
    target_score: float | None = None
    max_wallclock_s: int | None = None
    max_gpu_hours: float | None = None   # job mode: sum of job duration × gpus for this experiment
    root_eval: bool = True       # evaluate the starter to get the root score


@dataclass
class MemoryCfg:
    enabled: bool = True
    path: str = ""               # shared task wiki; relative paths resolve against experiment dir
    protocol_id: str = ""        # optional dataset/split version, in addition to evaluator/config hash
    reflect_every: int = 3       # completed records per synthesis
    batch_size: int = 8
    context_chars: int = 12000
    research_every: int = 3      # reserve every Nth expansion for a discriminating experiment; 0 disables
    patience_grace: int = 2      # bounded extra nodes at a score plateau, never a budget reset

    def __post_init__(self):
        if self.reflect_every < 1 or self.batch_size < 1 or self.context_chars < 2000:
            raise ValueError("memory requires reflect_every/batch_size >= 1 and context_chars >= 2000")
        if self.research_every < 0 or self.patience_grace < 0:
            raise ValueError("memory research_every/patience_grace must be nonnegative")


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
    # job mode (long-running evaluations through the job queue) ------------------------------------
    job_enabled: bool = False
    job_command: str = "{python} train.py --budget {budget} --run-dir {run_dir} {resume_flag}"   # cwd = worktree
    job_gpus: int = 0
    job_budgets: dict[str, float] = field(default_factory=dict)   # level -> budget (task-defined units, e.g. seconds)
    job_timeout_s: int = 3600
    job_stall_s: int = 600
    job_resumable: bool = False
    job_early_stop: dict[str, Any] = field(default_factory=dict)  # {warmup_frac, margin, patience_points}
    final_top_k: int = 1          # how many top nodes get the final (full) evaluation
    link_dirs: list[str] = field(default_factory=list)   # task-pack dirs symlinked into every repo/worktree (data, models)
    # "research": mechanism-first loop (discriminating ablations, belief revision); "competition": score-first
    # leaderboard workflow (prompts/competition.md), ablations only when they change a decision
    objective: str = "research"

    def __post_init__(self):
        if self.objective not in ("research", "competition"):
            raise ValueError(f"task objective must be 'research' or 'competition', got {self.objective!r}")

    @property
    def competition(self) -> bool:
        return self.objective == "competition"


@dataclass
class ExperimentCfg:
    name: str
    dir: Path
    task: TaskCfg
    runner: RunnerCfg = field(default_factory=RunnerCfg)
    utility: UtilityCfg = field(default_factory=UtilityCfg)
    search: SearchCfg = field(default_factory=SearchCfg)
    ops: OpsCfg = field(default_factory=OpsCfg)
    hooks: HooksCfg = field(default_factory=HooksCfg)
    memory: MemoryCfg = field(default_factory=MemoryCfg)
    research: ResearchCfg = field(default_factory=ResearchCfg)
    maintainer: MaintainerCfg = field(default_factory=MaintainerCfg)
    setup: SetupCfg = field(default_factory=SetupCfg)
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
    def setup_dir(self) -> Path:
        return self.dir / "setup"

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
            "ops": dataclasses.asdict(self.ops),
            "hooks": dataclasses.asdict(self.hooks),
            "memory": dataclasses.asdict(self.memory),
            "research": dataclasses.asdict(self.research),
            "maintainer": dataclasses.asdict(self.maintainer),
            "setup": dataclasses.asdict(self.setup),
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
        ops=_fill(OpsCfg, raw.get("ops", {})),
        hooks=_fill(HooksCfg, raw.get("hooks", {})),
        # Existing runs retain their search behavior until explicitly enabled.
        memory=_fill(MemoryCfg, raw.get("memory", {"enabled": False})),
        research=_fill(ResearchCfg, raw.get("research", {"enabled": False})),
        maintainer=_fill(MaintainerCfg, raw.get("maintainer", {"enabled": False})),
        # Research runs without a recorded setup must complete one before continuing.
        setup=_fill(SetupCfg, raw.get("setup", {})),
        notes=exp.get("notes", ""),
    )
