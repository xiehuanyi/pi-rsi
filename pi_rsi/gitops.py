"""Git plumbing: one branch + worktree per node; commits are the node's durable state."""
from __future__ import annotations

import shutil
from pathlib import Path

from .util import run_cmd


class GitError(RuntimeError):
    pass


def git(args: list[str], cwd: Path, check: bool = True, timeout: float = 120) -> str:
    p = run_cmd(["git", *args], cwd=cwd, timeout=timeout)
    if check and p.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed in {cwd}:\n{p.stderr.strip()}\n{p.stdout.strip()}")
    return p.stdout.strip()


def init_repo(repo: Path, message: str = "rsi: initial baseline") -> str:
    repo.mkdir(parents=True, exist_ok=True)
    if not (repo / ".git").exists():
        git(["init", "-q", "-b", "main"], cwd=repo)
        git(["config", "user.name", "pi-rsi"], cwd=repo)
        git(["config", "user.email", "pi-rsi@localhost"], cwd=repo)
        git(["config", "commit.gpgsign", "false"], cwd=repo)
    git(["add", "-A"], cwd=repo)
    if git(["status", "--porcelain"], cwd=repo):
        git(["commit", "-q", "-m", message], cwd=repo)
    return head(repo)


def head(repo: Path) -> str:
    return git(["rev-parse", "HEAD"], cwd=repo)


def short(sha: str | None) -> str:
    return (sha or "")[:8]


def add_worktree(repo: Path, worktree: Path, branch: str, base_commit: str) -> None:
    if worktree.exists():
        remove_worktree(repo, worktree, branch=None)
    # branch may exist from a previous attempt; recreate it at base
    branches = git(["branch", "--list", branch], cwd=repo)
    if branches:
        git(["branch", "-D", branch], cwd=repo)
    worktree.parent.mkdir(parents=True, exist_ok=True)
    git(["worktree", "add", "-q", "-b", branch, str(worktree), base_commit], cwd=repo)


def remove_worktree(repo: Path, worktree: Path, branch: str | None = None) -> None:
    try:
        git(["worktree", "remove", "--force", str(worktree)], cwd=repo, check=False)
    finally:
        if worktree.exists():
            shutil.rmtree(worktree, ignore_errors=True)
        git(["worktree", "prune"], cwd=repo, check=False)
    if branch:
        git(["branch", "-D", branch], cwd=repo, check=False)


def prune_ignored(worktree: Path, min_bytes: int) -> list[tuple[str, int]]:
    """Delete git-ignored regular files of at least `min_bytes` (caches, features, checkpoints) from a
    finished worktree. Symlinks (linked task data) and tracked files are never touched."""
    removed = []
    if not worktree.exists():
        return removed
    listing = git(["ls-files", "-z", "--others", "--ignored", "--exclude-standard"], cwd=worktree, check=False)
    for rel in filter(None, listing.split("\0")):
        path = worktree / rel
        try:
            st = path.lstat()
        except OSError:
            continue
        if path.is_symlink() or not path.is_file() or st.st_size < min_bytes:
            continue
        try:
            path.unlink()
            removed.append((rel, st.st_size))
        except OSError:
            pass
    return removed


def on_branch_between(worktree: Path, base: str, commit: str) -> bool:
    """`commit` exists, descends from `base` and is contained in HEAD (a state the worker committed)."""
    def ancestor(a, b):
        return run_cmd(["git", "merge-base", "--is-ancestor", a, b], cwd=worktree).returncode == 0
    return bool(commit) and ancestor(base, commit) and ancestor(commit, "HEAD")


def restore_tree(worktree: Path, commit: str) -> None:
    """Make the working tree and index exactly `commit`'s tree (files added later are removed)."""
    git(["restore", "--source", commit, "--staged", "--worktree", "--", ":/"], cwd=worktree)


def commit_all(worktree: Path, message: str) -> str | None:
    """Commit any pending changes; return new HEAD or None if nothing to commit."""
    git(["add", "-A"], cwd=worktree)
    if not git(["status", "--porcelain"], cwd=worktree):
        return None
    git(["commit", "-q", "-m", message], cwd=worktree)
    return head(worktree)


def changed_paths(worktree: Path, base: str, ref: str = "HEAD", pathspec: list[str] | None = None) -> list[str]:
    args = ["diff", "--name-only", base, ref]
    if pathspec:
        args += ["--", *pathspec]
    out = git(args, cwd=worktree, check=False)
    return [l for l in out.splitlines() if l.strip()]


def log_oneline(worktree: Path, base: str, ref: str = "HEAD", limit: int = 30) -> str:
    return git(["log", "--oneline", f"--max-count={limit}", f"{base}..{ref}"], cwd=worktree, check=False)


def diff_stat(worktree: Path, base: str, ref: str = "HEAD") -> str:
    return git(["diff", "--stat", base, ref], cwd=worktree, check=False)


def tag(repo: Path, name: str, commit: str, force: bool = True) -> None:
    args = ["tag", "-f" if force else "", name, commit]
    git([a for a in args if a], cwd=repo, check=False)
