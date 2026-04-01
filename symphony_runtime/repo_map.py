from dataclasses import dataclass


@dataclass(frozen=True)
class RepoMapping:
    project_key: str
    repo_key: str
    repo_path: str
    base_branch: str
