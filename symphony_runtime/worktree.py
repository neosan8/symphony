import subprocess
from pathlib import Path


def ensure_issue_worktree(repo_path: Path, worktree_path: Path, branch_name: str, base_branch: str) -> None:
    if worktree_path.exists():
        if not (worktree_path / ".git").exists():
            raise ValueError(f"Existing path is not a git worktree: {worktree_path}")
        return

    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "worktree", "add", str(worktree_path), "-b", branch_name, base_branch],
        cwd=repo_path,
        check=True,
    )
