"""RSI_HOME: where installed task packs and experiments live when pi-rsi is used as an installed tool.
Default ~/.pi-rsi. Inside a git checkout, the checkout's own tasks/ and experiments/ are used."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

PKG = Path(__file__).resolve().parent
REPO = PKG.parent
BUNDLED_TASKS = PKG / "tasks"


def home() -> Path:
    return Path(os.environ.get("RSI_HOME", str(Path.home() / ".pi-rsi"))).expanduser()


def in_checkout() -> bool:
    return (REPO / "pyproject.toml").exists() and (REPO / ".git").exists()


def tasks_dir() -> Path:
    return BUNDLED_TASKS if in_checkout() else home() / "tasks"


def experiments_dir() -> Path:
    return (REPO / "experiments") if in_checkout() else home() / "experiments"


def list_bundled() -> list[str]:
    return sorted(p.name for p in BUNDLED_TASKS.iterdir() if (p / "task.toml").exists())


def install_task(name: str, force: bool = False, setup: bool = True) -> Path:
    """Copy a bundled task pack into RSI_HOME/tasks/<name> (or use it in place inside a checkout) and run its setup.sh."""
    src = BUNDLED_TASKS / name
    if not (src / "task.toml").exists():
        raise FileNotFoundError(f"no bundled task pack named {name}; available: {', '.join(list_bundled())}")
    dst = src if in_checkout() else home() / "tasks" / name
    if dst != src:
        if dst.exists() and not force:
            pass
        else:
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".venv", "__pycache__", "data", "private"))
    if setup and (dst / "setup.sh").exists() and not (dst / ".venv").exists():
        import subprocess
        subprocess.run(["bash", str(dst / "setup.sh")], check=True)
    return dst


def resolve_task(spec: str) -> Path:
    """A task spec is a directory path or the name of a bundled/installed pack."""
    p = Path(spec).expanduser()
    if (p / "task.toml").exists():
        return p.resolve()
    installed = tasks_dir() / spec
    if (installed / "task.toml").exists():
        return installed.resolve()
    if (BUNDLED_TASKS / spec / "task.toml").exists():
        return install_task(spec)
    raise FileNotFoundError(f"task pack not found: {spec} (bundled: {', '.join(list_bundled())})")
