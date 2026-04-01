import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from symphony_runtime.config import SymphonyConfig
from symphony_runtime.daemon import SymphonyRuntime
from symphony_runtime.models import LinearIssue
from symphony_runtime.preflight import PreflightResult
from symphony_runtime.repo_map import RepoMapping


class RuntimeOnceExecuteTests(unittest.TestCase):
    def test_run_once_execute_uses_real_prepare_flow_and_writes_execution_artifacts(self):
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
            runtime.linear_client = Mock()
            runtime.fetch_candidate_issues = Mock(return_value=[
                LinearIssue(
                    id="issue-id-123",
                    identifier="LIN-42",
                    title="Fix output",
                    description="Body",
                    status="Todo",
                    labels=["agent-ready"],
                    project_key="symphony",
                )
            ])
            repo_path = workspace_root / "repo"
            repo_path.mkdir()
            runtime.load_repo_map = Mock(return_value={
                "symphony": RepoMapping(
                    project_key="symphony",
                    repo_key="symphony",
                    repo_path=str(repo_path),
                    base_branch="main",
                )
            })
            runtime.load_repo_contract = Mock(return_value={"boot": "python3 symphony_v2.py", "test": "python3 -m unittest discover -s tests -p 'test_*.py' -v"})

            with patch.object(SymphonyRuntime, "_build_branch_name", return_value="feature/lin-42"), patch.object(
                SymphonyRuntime, "_resolve_base_branch", return_value="main"
            ), patch("symphony_runtime.daemon.ensure_issue_worktree") as ensure_issue_worktree, patch(
                "symphony_runtime.daemon.run_preflight",
                return_value=PreflightResult(ok=True),
            ), patch(
                "symphony_runtime.daemon.run_codex_command",
                return_value=0,
            ) as run_codex_command, patch(
                "symphony_runtime.daemon.resolve_head_commit",
                return_value="abc123def456",
            ) as resolve_head_commit:
                preview = runtime.run_once_execute()

            run_root = workspace_root / "runs" / "lin-42"
            self.assertIn("Execution finished for Fix output", preview)
            self.assertIn("Codex execution finished successfully.", preview)
            self.assertIn("Commit: abc123def456", preview)
            self.assertTrue((run_root / "context.md").exists())
            self.assertTrue((run_root / "human_gate.md").exists())
            self.assertEqual((run_root / "summary.md").read_text(), "Execution finished for Fix output")
            status_payload = json.loads((run_root / "status.json").read_text())
            self.assertEqual(status_payload["status"], "human_gate")
            self.assertEqual(status_payload["issue_id"], "issue-id-123")
            self.assertEqual(status_payload["issue_key"], "LIN-42")
            self.assertEqual(status_payload["branch"], "feature/lin-42")
            self.assertEqual(status_payload["worktree_path"], str(workspace_root / "worktrees" / "lin-42"))
            self.assertEqual(status_payload["base_branch"], "main")
            self.assertEqual(status_payload["commit_sha"], "abc123def456")
            self.assertEqual(status_payload["return_code"], 0)
            self.assertEqual(
                status_payload["human_gate"],
                {
                    "recommendation": "review",
                    "decision_required": True,
                    "decision_applied": False,
                    "package_json_path": "human_gate_package.json",
                    "package_markdown_path": "human_gate_package.md",
                },
            )
            state_payload = json.loads((run_root / "state.json").read_text())
            self.assertEqual(state_payload["issue_id"], "issue-id-123")
            self.assertEqual(state_payload["issue_key"], "LIN-42")
            self.assertEqual(state_payload["branch"], "feature/lin-42")
            self.assertEqual(state_payload["worktree_path"], str(workspace_root / "worktrees" / "lin-42"))
            self.assertEqual(state_payload["base_branch"], "main")
            self.assertEqual(state_payload["commit_sha"], "abc123def456")
            self.assertEqual(
                state_payload["human_gate"],
                {
                    "recommendation": "review",
                    "decision_required": True,
                    "decision_applied": False,
                    "package_json_path": "human_gate_package.json",
                    "package_markdown_path": "human_gate_package.md",
                },
            )
            ensure_issue_worktree.assert_called_once_with(
                repo_path,
                workspace_root / "worktrees" / "lin-42",
                branch_name="feature/lin-42",
                base_branch="main",
            )
            run_codex_command.assert_called_once()
            resolve_head_commit.assert_called_once_with(workspace_root / "worktrees" / "lin-42")

    def test_run_once_execute_marks_failed_execution_in_summary_and_state(self):
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
            runtime.linear_client = Mock()
            runtime.fetch_candidate_issues = Mock(return_value=[
                LinearIssue(
                    id="issue-id-123",
                    identifier="LIN-42",
                    title="Fix output",
                    description="Body",
                    status="Todo",
                    labels=["agent-ready"],
                    project_key="symphony",
                )
            ])
            repo_path = workspace_root / "repo"
            repo_path.mkdir()
            runtime.load_repo_map = Mock(return_value={
                "symphony": RepoMapping(
                    project_key="symphony",
                    repo_key="symphony",
                    repo_path=str(repo_path),
                    base_branch="main",
                )
            })
            runtime.load_repo_contract = Mock(return_value={"boot": "python3 symphony_v2.py", "test": "python3 -m unittest discover -s tests -p 'test_*.py' -v"})

            with patch.object(SymphonyRuntime, "_build_branch_name", return_value="feature/lin-42"), patch.object(
                SymphonyRuntime, "_resolve_base_branch", return_value="main"
            ), patch("symphony_runtime.daemon.ensure_issue_worktree"), patch(
                "symphony_runtime.daemon.run_preflight",
                return_value=PreflightResult(ok=True),
            ), patch(
                "symphony_runtime.daemon.run_codex_command",
                return_value=7,
            ), patch(
                "symphony_runtime.daemon.resolve_head_commit",
                return_value="deadbeef987654",
            ):
                preview = runtime.run_once_execute()

            run_root = workspace_root / "runs" / "lin-42"
            self.assertIn("Execution failed for Fix output", preview)
            self.assertIn("Codex execution exited with code 7.", preview)
            self.assertIn("Commit: deadbeef987654", preview)
            self.assertEqual((run_root / "summary.md").read_text(), "Execution failed for Fix output")
            state_payload = json.loads((run_root / "state.json").read_text())
            status_payload = json.loads((run_root / "status.json").read_text())
            self.assertEqual(state_payload["status"], "human_gate")
            self.assertEqual(status_payload["status"], "human_gate")
            self.assertEqual(state_payload["issue_id"], "issue-id-123")
            self.assertEqual(status_payload["issue_id"], "issue-id-123")
            self.assertEqual(state_payload["issue_key"], "LIN-42")
            self.assertEqual(status_payload["issue_key"], "LIN-42")
            self.assertEqual(state_payload["commit_sha"], "deadbeef987654")
            self.assertEqual(status_payload["commit_sha"], "deadbeef987654")
            self.assertEqual(state_payload["return_code"], 7)
            self.assertEqual(status_payload["return_code"], 7)
            self.assertEqual(state_payload["branch"], "feature/lin-42")
            self.assertEqual(status_payload["branch"], "feature/lin-42")
            self.assertEqual(
                state_payload["human_gate"],
                {
                    "recommendation": "review",
                    "decision_required": True,
                    "decision_applied": False,
                    "package_json_path": "human_gate_package.json",
                    "package_markdown_path": "human_gate_package.md",
                },
            )
            self.assertEqual(
                status_payload["human_gate"],
                {
                    "recommendation": "review",
                    "decision_required": True,
                    "decision_applied": False,
                    "package_json_path": "human_gate_package.json",
                    "package_markdown_path": "human_gate_package.md",
                },
            )

    def test_run_once_execute_falls_back_when_head_resolution_fails(self):
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
            runtime.linear_client = Mock()
            runtime.fetch_candidate_issues = Mock(return_value=[
                LinearIssue(
                    id="issue-id-123",
                    identifier="LIN-42",
                    title="Fix output",
                    description="Body",
                    status="Todo",
                    labels=["agent-ready"],
                    project_key="symphony",
                )
            ])
            repo_path = workspace_root / "repo"
            repo_path.mkdir()
            runtime.load_repo_map = Mock(return_value={
                "symphony": RepoMapping(
                    project_key="symphony",
                    repo_key="symphony",
                    repo_path=str(repo_path),
                    base_branch="main",
                )
            })
            runtime.load_repo_contract = Mock(return_value={"boot": "python3 symphony_v2.py", "test": "python3 -m unittest discover -s tests -p 'test_*.py' -v"})

            with patch.object(SymphonyRuntime, "_build_branch_name", return_value="feature/lin-42"), patch.object(
                SymphonyRuntime, "_resolve_base_branch", return_value="main"
            ), patch("symphony_runtime.daemon.ensure_issue_worktree"), patch(
                "symphony_runtime.daemon.run_preflight",
                return_value=PreflightResult(ok=True),
            ), patch(
                "symphony_runtime.daemon.run_codex_command",
                return_value=0,
            ), patch(
                "symphony_runtime.daemon.resolve_head_commit",
                side_effect=RuntimeError("Could not resolve HEAD"),
            ):
                preview = runtime.run_once_execute()

            run_root = workspace_root / "runs" / "lin-42"
            self.assertIn("Execution finished for Fix output", preview)
            self.assertIn("Commit: unresolved-head", preview)
            self.assertTrue((run_root / "human_gate.md").exists())
            self.assertEqual((run_root / "summary.md").read_text(), "Execution finished for Fix output")
            status_payload = json.loads((run_root / "status.json").read_text())
            state_payload = json.loads((run_root / "state.json").read_text())
            self.assertEqual(status_payload["status"], "human_gate")
            self.assertEqual(
                status_payload["human_gate"],
                {
                    "recommendation": "review",
                    "decision_required": True,
                    "decision_applied": False,
                    "package_json_path": "human_gate_package.json",
                    "package_markdown_path": "human_gate_package.md",
                },
            )
            self.assertEqual(
                state_payload["human_gate"],
                {
                    "recommendation": "review",
                    "decision_required": True,
                    "decision_applied": False,
                    "package_json_path": "human_gate_package.json",
                    "package_markdown_path": "human_gate_package.md",
                },
            )


if __name__ == "__main__":
    unittest.main()
