import json
import tempfile
import unittest
from pathlib import Path

from symphony_runtime.repo_contract import CONTRACT_FILENAME, load_repo_contract


class RepoContractTests(unittest.TestCase):
    def test_load_repo_contract_returns_parsed_json_from_repo_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            contract_path = repo_path / CONTRACT_FILENAME
            expected = {
                "boot": "python -m symphony_runtime",
                "test": "python -m unittest",
                "env": {"MODE": "test"},
            }
            contract_path.write_text(json.dumps(expected))

            self.assertEqual(load_repo_contract(repo_path), expected)
