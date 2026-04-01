import json
from pathlib import Path

from symphony_runtime.repo_map import RepoMapping


def load_repo_map(path: Path) -> dict[str, RepoMapping]:
    payload = json.loads(path.read_text())
    projects = payload.get("projects", {})
    return {
        project_key: RepoMapping(
            project_key=project_key,
            repo_key=project["repo_key"],
            repo_path=project["repo_path"],
            base_branch=project["base_branch"],
        )
        for project_key, project in projects.items()
    }
