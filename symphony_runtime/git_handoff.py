from __future__ import annotations

from pathlib import Path
import subprocess


def resolve_head_commit(worktree_path: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=worktree_path,
        capture_output=True,
        text=True,
    )
    sha = (result.stdout or "").strip()
    if result.returncode != 0 or not sha:
        stderr = (result.stderr or "").strip()
        detail = f": {stderr}" if stderr else ""
        raise RuntimeError(f"Could not resolve HEAD in {worktree_path}{detail}")
    return sha
