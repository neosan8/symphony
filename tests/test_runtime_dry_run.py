import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from symphony_runtime.config import SymphonyConfig
from symphony_runtime.daemon import SymphonyRuntime
from symphony_runtime.models import LinearIssue
from symphony_runtime.repo_map import RepoMapping


class RuntimeDryRunTests(unittest.TestCase):
    def test_resolve_base_branch_raises_when_branch_cannot_be_verified(self):
        repo_path = Path("/tmp/repo")
        failure = subprocess.CompletedProcess(
            args=["git", "rev-parse", "--verify", "missing-branch"],
            returncode=1,
            stdout="",
            stderr="fatal: Needed a single revision\n",
        )

        with patch("symphony_runtime.daemon.subprocess.run", return_value=failure) as run_mock:
            with self.assertRaisesRegex(LookupError, "missing-branch"):
                SymphonyRuntime._resolve_base_branch(repo_path, "missing-branch")

        run_mock.assert_called_once_with(
            ["git", "rev-parse", "--verify", "missing-branch"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

    def test_prepare_issue_run_writes_context_and_state_with_verified_base_branch(self):
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
                links=["https://example.test/spec"],
            )
            repo_path = workspace_root / "repo"
            repo_path.mkdir()
            mapping = RepoMapping(
                project_key="symphony",
                repo_key="symphony",
                repo_path=str(repo_path),
                base_branch="main",
            )
            contract = {"boot": "python3 symphony_v2.py", "test": "python3 -m unittest discover -s tests -p 'test_*.py' -v"}

            with patch.object(SymphonyRuntime, "_build_branch_name", return_value="feature/lin-42"), patch.object(
                SymphonyRuntime, "_resolve_base_branch", return_value="main"
            ) as resolve_base_branch, patch("symphony_runtime.daemon.ensure_issue_worktree") as ensure_issue_worktree:
                result = runtime.prepare_issue_run(issue, mapping, contract)

            self.assertTrue((result["run_root"] / "state.json").exists())
            self.assertTrue((result["run_root"] / "context.md").exists())
            self.assertEqual(result["branch_name"], "feature/lin-42")
            self.assertEqual(result["command"][0], "codex")
            resolve_base_branch.assert_called_once_with(repo_path, "main")
            ensure_issue_worktree.assert_called_once_with(
                repo_path,
                result["worktree_path"],
                branch_name="feature/lin-42",
                base_branch="main",
            )

    def test_prepare_issue_run_raises_when_base_branch_cannot_be_verified(self):
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
                links=["https://example.test/spec"],
            )
            repo_path = workspace_root / "repo"
            repo_path.mkdir()
            mapping = RepoMapping(
                project_key="symphony",
                repo_key="symphony",
                repo_path=str(repo_path),
                base_branch="missing-branch",
            )
            contract = {"boot": "python3 symphony_v2.py", "test": "python3 -m unittest discover -s tests -p 'test_*.py' -v"}

            with patch.object(SymphonyRuntime, "_build_branch_name", return_value="feature/lin-42"), patch.object(
                SymphonyRuntime,
                "_resolve_base_branch",
                side_effect=LookupError("Configured base branch 'missing-branch' does not exist in /tmp/repo"),
            ), patch("symphony_runtime.daemon.ensure_issue_worktree") as ensure_issue_worktree:
                with self.assertRaisesRegex(LookupError, "missing-branch"):
                    runtime.prepare_issue_run(issue, mapping, contract)

            ensure_issue_worktree.assert_not_called()
            self.assertTrue((workspace_root / "runs" / "lin-42" / "state.json").exists())
            self.assertFalse((workspace_root / "runs" / "lin-42" / "context.md").exists())
