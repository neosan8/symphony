from pathlib import Path
from typing import Any
import json


CONTRACT_FILENAME = "repo-contract.json"


def load_repo_contract(repo_path: Path) -> dict[str, Any]:
    return json.loads((repo_path / CONTRACT_FILENAME).read_text())
