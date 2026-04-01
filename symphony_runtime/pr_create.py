"""Create GitHub pull requests for a prepared worktree.

Assumptions:
- the branch is pushed to the git remote named ``origin``
- GitHub CLI (``gh``) is installed and authenticated in the runtime environment
"""

from __future__ import annotations

from pathlib import Path
import subprocess


def _run_command(worktree_path: Path, command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=worktree_path,
        capture_output=True,
        text=True,
    )


def ensure_ready_for_pr(worktree_path: Path, expected_commit: str, expected_branch: str) -> None:
    head_result = _run_command(worktree_path, ["git", "rev-parse", "--verify", "HEAD"])
    head_commit = (head_result.stdout or "").strip()
    if head_result.returncode != 0 or not head_commit:
        stderr = (head_result.stderr or "").strip()
        detail = f": {stderr}" if stderr else ""
        raise RuntimeError(f"Could not resolve HEAD in {worktree_path}{detail}")
    if head_commit != expected_commit:
        raise RuntimeError(f"Expected HEAD {expected_commit}, found {head_commit}")

    branch_result = _run_command(worktree_path, ["git", "branch", "--show-current"])
    branch_name = (branch_result.stdout or "").strip()
    if branch_result.returncode != 0 or not branch_name:
        stderr = (branch_result.stderr or "").strip()
        detail = f": {stderr}" if stderr else ""
        raise RuntimeError(f"Could not resolve current branch in {worktree_path}{detail}")
    if branch_name != expected_branch:
        raise RuntimeError(f"Expected branch {expected_branch}, found {branch_name}")


def create_pull_request(
    worktree_path: Path,
    base_branch: str,
    head_branch: str,
    title: str,
    body_path: Path,
) -> str:
    """Push ``head_branch`` to ``origin`` and open a PR with the ``gh`` CLI."""
    push_result = _run_command(worktree_path, ["git", "push", "-u", "origin", head_branch])
    if push_result.returncode != 0:
        stderr = (push_result.stderr or "").strip()
        detail = f": {stderr}" if stderr else ""
        raise RuntimeError(f"Failed to push branch {head_branch} to origin{detail}")

    pr_result = _run_command(
        worktree_path,
        [
            "gh",
            "pr",
            "create",
            "--base",
            base_branch,
            "--head",
            head_branch,
            "--title",
            title,
            "--body-file",
            str(body_path),
        ],
    )
    pr_url = (pr_result.stdout or "").strip()
    if pr_result.returncode != 0 or not pr_url:
        stderr = (pr_result.stderr or "").strip()
        detail = f": {stderr}" if stderr else ""
        raise RuntimeError(f"Failed to create pull request with gh{detail}")
    return pr_url
