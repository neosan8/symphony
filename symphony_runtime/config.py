from __future__ import annotations

import os
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

    @classmethod
    def default(cls) -> "SymphonyConfig":
        workspace_root_override = os.environ.get("SYMPHONY_WORKSPACE_ROOT")
        if workspace_root_override:
            workspace_root = Path(workspace_root_override).expanduser()
        else:
            workspace_root = Path.home() / ".openclaw" / "workspace"
        return cls(
            workspace_root=workspace_root,
            config_root=workspace_root / "config" / "symphony",
            runs_root=workspace_root / "symphony-runs",
            worktrees_root=workspace_root / "worktrees",
        )
