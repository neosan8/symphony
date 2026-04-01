import json
import tempfile
import unittest
from pathlib import Path

from symphony_runtime.config_loader import load_repo_map
from symphony_runtime.repo_map import RepoMapping


class ConfigLoaderTests(unittest.TestCase):
    def test_load_repo_map_returns_typed_project_mappings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "repos.json"
            path.write_text(json.dumps({
                "projects": {
                    "mobile-core": {
                        "repo_key": "symphony",
                        "repo_path": "/Users/neosan/Documents/symphony",
                        "base_branch": "main"
                    }
                }
            }))

            loaded = load_repo_map(path)

            self.assertEqual(
                loaded["mobile-core"],
                RepoMapping(
                    project_key="mobile-core",
                    repo_key="symphony",
                    repo_path="/Users/neosan/Documents/symphony",
                    base_branch="main",
                ),
            )

    def test_repo_tracked_example_config_matches_loader_contract(self):
        example_path = Path(__file__).resolve().parents[1] / "config" / "repos.example.json"

        loaded = load_repo_map(example_path)

        self.assertIn("mobile-core", loaded)
        self.assertIsInstance(loaded["mobile-core"], RepoMapping)
