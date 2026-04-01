from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


@dataclass(frozen=True)
class LinearIssue:
    id: str
    identifier: str
    title: str
    status: str
    description: str = ""
    labels: list[str] = field(default_factory=list)
    project_key: str = ""
    comments: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        for field_name in ("id", "identifier", "title", "status"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"LinearIssue.{field_name} must be a non-empty string")


class RunStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    HUMAN_GATE = "human_gate"
    BLOCKED = "blocked"
    DONE = "done"


@dataclass(frozen=True)
class ReviewerResult:
    approved: bool
    findings: list[str]
    raw_output: str
    iterations: int


@dataclass(frozen=True)
class ExecutionResult:
    issue_key: str
    run_root: Path
    worktree_path: Path
    branch_name: str
    command: tuple[str, ...]
    return_code: int
    stdout_path: Path
    stderr_path: Path
    preflight_ok: bool
