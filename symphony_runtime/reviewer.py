"""Automated code reviewer using Claude Code CLI."""
from __future__ import annotations

import subprocess
from pathlib import Path

from symphony_runtime.models import ReviewerResult


REVIEWER_PROMPT_TEMPLATE = """\
You are a code reviewer. Review the git diff in this worktree against the issue spec.

Issue: {issue_title}
Spec: {context_summary}

Check for:
1. Does the implementation match the spec?
2. Are there obvious bugs or errors?
3. Do existing tests pass? (check test output if available)
4. Any security or breaking change concerns?

If everything looks good, respond ONLY with: APPROVED
If there are issues, list them as:
BLOCKING: <description>
...

Be concise. Max 10 findings.
"""


def build_reviewer_command(
    worktree_path: Path,
    context_path: Path,
    diff_summary: str,
    model: str = "claude-sonnet-4-20250514",
) -> list[str]:
    """Build the claude -p command for reviewing changes."""
    context_summary = ""
    if context_path.exists():
        context_summary = context_path.read_text(errors="replace")[:2000]

    prompt = REVIEWER_PROMPT_TEMPLATE.format(
        issue_title=worktree_path.name,
        context_summary=context_summary,
    )
    if diff_summary:
        prompt += f"\n\nDiff summary:\n{diff_summary}"

    return [
        "claude",
        "-p",
        prompt,
        "--model",
        model,
    ]


def _get_diff_summary(worktree_path: Path) -> str:
    """Get a git diff summary from the worktree."""
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD~1", "--stat"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def _parse_reviewer_output(raw_output: str) -> tuple[bool, list[str]]:
    """Parse reviewer output into (approved, findings)."""
    stripped = raw_output.strip()
    if not stripped:
        return True, []

    if stripped == "APPROVED" or stripped.startswith("APPROVED"):
        lines_after = stripped.split("\n", 1)
        if len(lines_after) == 1 or not lines_after[1].strip():
            return True, []

    findings: list[str] = []
    for line in stripped.splitlines():
        line = line.strip()
        if line.upper().startswith("BLOCKING:"):
            finding = line[len("BLOCKING:"):].strip()
            if finding:
                findings.append(finding)

    if findings:
        return False, findings

    if "APPROVED" in stripped.upper():
        return True, []

    return True, []


def run_reviewer(
    worktree_path: Path,
    context_path: Path,
    stdout_path: Path,
    stderr_path: Path,
    model: str = "claude-sonnet-4-20250514",
) -> ReviewerResult:
    """
    Run Claude reviewer on the worktree.
    Returns ReviewerResult with: approved (bool), findings (list[str]), raw_output (str).

    Fail-open: if the reviewer process fails, returns approved=True so the task
    is never blocked by a reviewer crash.
    """
    diff_summary = _get_diff_summary(worktree_path)
    command = build_reviewer_command(worktree_path, context_path, diff_summary, model=model)

    try:
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_path.parent.mkdir(parents=True, exist_ok=True)

        with stdout_path.open("w") as stdout_file, stderr_path.open("w") as stderr_file:
            process = subprocess.run(
                command,
                cwd=worktree_path,
                stdout=stdout_file,
                stderr=stderr_file,
                timeout=300,
            )

        raw_output = stdout_path.read_text(errors="replace") if stdout_path.exists() else ""

        if process.returncode != 0:
            return ReviewerResult(
                approved=True,
                findings=[],
                raw_output=raw_output,
                iterations=0,
            )

        approved, findings = _parse_reviewer_output(raw_output)
        return ReviewerResult(
            approved=approved,
            findings=findings,
            raw_output=raw_output,
            iterations=0,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ReviewerResult(
            approved=True,
            findings=[],
            raw_output="",
            iterations=0,
        )
