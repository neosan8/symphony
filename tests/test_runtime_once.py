import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from symphony_runtime.config import SymphonyConfig
from symphony_runtime.daemon import SymphonyRuntime
from symphony_runtime.models import LinearIssue
from symphony_runtime.preflight import PreflightResult
from symphony_runtime.repo_map import RepoMapping


class RuntimeOnceTests(unittest.TestCase):
    def test_run_once_dry_uses_repo_specific_contract_and_prepare_issue_run_result(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir)
            runtime = SymphonyRuntime(
                config=SymphonyConfig(
                    workspace_root=workspace_root,
                    config_root=workspace_root / "config",
                    runs_root=workspace_root / "runs",
                    worktrees_root=workspace_root / "worktrees",
                )
            )
            runtime.ensure_workspace_roots()
            issue = LinearIssue(
                id="issue-id-123",
                identifier="LIN-42",
                title="Fix output",
                description="Body",
                status="Todo",
                labels=["agent-ready"],
                project_key="symphony",
            )
            mapping = RepoMapping(
                project_key="symphony",
                repo_key="symphony",
                repo_path=str(workspace_root / "repos" / "symphony"),
                base_branch="main",
            )
            repo_contract = {
                "boot": "python3 symphony_v2.py",
                "test": "python3 -m unittest discover -s tests -p 'test_*.py' -v",
            }
            prep_result = {
                "run_root": workspace_root / "runs" / "lin-42",
                "worktree_path": workspace_root / "worktrees" / "lin-42",
                "branch_name": "feature/lin-42",
                "command": ["codex", "exec"],
                "preflight": PreflightResult(True, ""),
            }
            prep_result["run_root"].mkdir(parents=True)

            runtime.fetch_candidate_issues = Mock(return_value=[issue])
            runtime.load_repo_map = Mock(return_value={"symphony": mapping})
            runtime.load_repo_contract = Mock(return_value=repo_contract)
            runtime.prepare_issue_run = Mock(return_value=prep_result)

            preview = runtime.run_once_dry()

            runtime.load_repo_contract.assert_called_once_with(mapping)
            runtime.prepare_issue_run.assert_called_once_with(issue, mapping, repo_contract)
            self.assertEqual(
                preview,
                (prep_result["run_root"] / "human_gate.md").read_text(),
            )
            self.assertIn("Human Gate for LIN-42", preview)
            self.assertIn("Recommendation: review", preview)
            self.assertIn("Verification:\nPreflight passed", preview)
            self.assertIn("Branch: feature/lin-42", preview)
            self.assertIn("Review:\nDry-run only; Codex command prepared but not executed.", preview)
