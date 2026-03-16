from __future__ import annotations

import subprocess
from pathlib import Path


def fetch_pr_review_comments(pr_url: str, worktree_path: Path) -> str:
    """Fetch PR review data as JSON via `gh pr view`.

    Task 3 contract assumptions:
    - gh CLI must be installed and available on PATH
    - gh must already be authenticated for the target GitHub host
    - pr_url must be a valid GitHub pull request URL
    """
    if not isinstance(pr_url, str) or not pr_url:
        raise ValueError("pr_url must be a non-empty string")

    result = subprocess.run(
        [
            "gh",
            "pr",
            "view",
            pr_url,
            "--comments",
            "--json",
            "comments,reviews",
        ],
        cwd=worktree_path,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        message = (result.stderr or result.stdout or "gh pr view failed").strip()
        raise RuntimeError(f"Failed to fetch PR review comments: {message}")

    output = result.stdout.strip()
    if not output:
        raise RuntimeError("Failed to fetch PR review comments: gh returned empty output")

    return output
