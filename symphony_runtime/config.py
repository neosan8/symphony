from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SymphonyConfig:
    workspace_root: Path
    config_root: Path
    runs_root: Path
    worktrees_root: Path
    poll_interval_seconds: int = 30
    max_concurrency: int = 2
    max_repo_concurrency: int = 1
    reviewer_enabled: bool = True
    reviewer_max_iterations: int = 3
    reviewer_model: str = "claude-sonnet-4-20250514"

    @classmethod
    def default(cls) -> "SymphonyConfig":
        workspace_root = Path("/Users/neosan/.openclaw/workspace")
        return cls(
            workspace_root=workspace_root,
            config_root=workspace_root / "config" / "symphony",
            runs_root=workspace_root / "symphony-runs",
            worktrees_root=workspace_root / "worktrees",
        )
