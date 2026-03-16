import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from symphony_runtime.config import SymphonyConfig
from symphony_runtime.daemon import SymphonyRuntime
from symphony_runtime.models import LinearIssue
from symphony_runtime.preflight import PreflightResult
from symphony_runtime.repo_map import RepoMapping


class RuntimeLinearFeedbackTests(unittest.TestCase):
    def _build_runtime(self, tmpdir: str) -> SymphonyRuntime:
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
        return runtime

    def test_sync_started_posts_built_comment_body(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = self._build_runtime(tmpdir)

            runtime.sync_started("issue-id-123", "LIN-42", "feature/lin-42")

            runtime.linear_client.add_comment.assert_called_once_with(
                "issue-id-123",
                "Execution started for LIN-42\nBranch: feature/lin-42",
            )

    def test_sync_blocked_posts_expected_comment(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = self._build_runtime(tmpdir)

            runtime.sync_blocked("issue-id-123", "LIN-42", "preflight failed")

            runtime.linear_client.add_comment.assert_called_once_with(
                "issue-id-123",
                "Execution blocked for LIN-42\nReason: preflight failed",
            )

    def test_sync_human_gate_builds_comment_from_runtime_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = self._build_runtime(tmpdir)

            runtime.sync_human_gate(
                issue_id="issue-id-123",
                issue_key="LIN-42",
                branch="feature/lin-42",
                commit_sha="abc123def456",
                recommendation="review",
                summary="Execution finished for Fix output",
                verification="Codex execution finished successfully.",
                review="Review stdout at /tmp/stdout.log\nReview stderr at /tmp/stderr.log",
            )

            runtime.linear_client.add_comment.assert_called_once_with(
                "issue-id-123",
                "\n".join(
                    [
                        "Human Gate for LIN-42",
                        "Recommendation: review",
                        "Branch: feature/lin-42",
                        "Commit: abc123def456",
                        "",
                        "Summary:",
                        "Execution finished for Fix output",
                        "",
                        "Verification:",
                        "Codex execution finished successfully.",
                        "",
                        "Review:",
                        "Review stdout at /tmp/stdout.log\nReview stderr at /tmp/stderr.log",
                    ]
                ),
            )

    def test_run_once_execute_posts_started_and_human_gate_comments(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = self._build_runtime(tmpdir)
            workspace_root = Path(tmpdir)
            issue = LinearIssue(
                id="issue-id-123",
                identifier="LIN-42",
                title="Fix output",
                description="Body",
                status="Todo",
                labels=["agent-ready"],
                project_key="symphony",
            )
            repo_path = workspace_root / "repo"
            repo_path.mkdir()
            runtime.fetch_candidate_issues = Mock(return_value=[issue])
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
                return_value="abc123def456",
            ):
                runtime.run_once_execute()

            self.assertEqual(runtime.linear_client.add_comment.call_count, 2)
            runtime.linear_client.add_comment.assert_any_call(
                "issue-id-123",
                "Execution started for LIN-42\nBranch: feature/lin-42",
            )
            runtime.linear_client.add_comment.assert_any_call(
                "issue-id-123",
                "\n".join(
                    [
                        "Human Gate for LIN-42",
                        "Recommendation: review",
                        "Branch: feature/lin-42",
                        "Commit: abc123def456",
                        "",
                        "Summary:",
                        "Execution finished for Fix output",
                        "",
                        "Verification:",
                        "Codex execution finished successfully.",
                        "",
                        "Review:",
                        f"Review stdout at {workspace_root / 'runs' / 'lin-42' / 'logs' / 'stdout.log'}\nReview stderr at {workspace_root / 'runs' / 'lin-42' / 'logs' / 'stderr.log'}",
                    ]
                ),
            )

    def test_run_once_execute_marks_issue_in_progress_when_execution_starts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = self._build_runtime(tmpdir)
            workspace_root = Path(tmpdir)
            issue = LinearIssue(
                id="issue-id-123",
                identifier="LIN-42",
                title="Fix output",
                description="Body",
                status="Todo",
                labels=["agent-ready"],
                project_key="symphony",
            )
            repo_path = workspace_root / "repo"
            repo_path.mkdir()
            runtime.fetch_candidate_issues = Mock(return_value=[issue])
            runtime.load_repo_map = Mock(return_value={
                "symphony": RepoMapping(
                    project_key="symphony",
                    repo_key="symphony",
                    repo_path=str(repo_path),
                    base_branch="main",
                )
            })
            runtime.load_repo_contract = Mock(return_value={"boot": "python3 symphony_v2.py", "test": "python3 -m unittest discover -s tests -p 'test_*.py' -v"})
            runtime.sync_status = Mock(return_value=True)

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
                return_value="abc123def456",
            ):
                runtime.run_once_execute()

            runtime.sync_status.assert_any_call("issue-id-123", "In Progress")

    def test_run_once_execute_posts_blocked_comment_when_preflight_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = self._build_runtime(tmpdir)
            workspace_root = Path(tmpdir)
            issue = LinearIssue(
                id="issue-id-123",
                identifier="LIN-42",
                title="Fix output",
                description="Body",
                status="Todo",
                labels=["agent-ready"],
                project_key="symphony",
            )
            repo_path = workspace_root / "repo"
            repo_path.mkdir()
            runtime.fetch_candidate_issues = Mock(return_value=[issue])
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
                return_value=PreflightResult(ok=False, reason="missing secret"),
            ):
                with self.assertRaisesRegex(ValueError, "preflight failed"):
                    runtime.run_once_execute()

            runtime.linear_client.add_comment.assert_called_once_with(
                "issue-id-123",
                "Execution blocked for LIN-42\nReason: missing secret",
            )

    def test_run_once_execute_marks_issue_blocked_when_preflight_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = self._build_runtime(tmpdir)
            workspace_root = Path(tmpdir)
            issue = LinearIssue(
                id="issue-id-123",
                identifier="LIN-42",
                title="Fix output",
                description="Body",
                status="Todo",
                labels=["agent-ready"],
                project_key="symphony",
            )
            repo_path = workspace_root / "repo"
            repo_path.mkdir()
            runtime.fetch_candidate_issues = Mock(return_value=[issue])
            runtime.load_repo_map = Mock(return_value={
                "symphony": RepoMapping(
                    project_key="symphony",
                    repo_key="symphony",
                    repo_path=str(repo_path),
                    base_branch="main",
                )
            })
            runtime.load_repo_contract = Mock(return_value={"boot": "python3 symphony_v2.py", "test": "python3 -m unittest discover -s tests -p 'test_*.py' -v"})
            runtime.sync_status = Mock(return_value=True)

            with patch.object(SymphonyRuntime, "_build_branch_name", return_value="feature/lin-42"), patch.object(
                SymphonyRuntime, "_resolve_base_branch", return_value="main"
            ), patch("symphony_runtime.daemon.ensure_issue_worktree"), patch(
                "symphony_runtime.daemon.run_preflight",
                return_value=PreflightResult(ok=False, reason="missing secret"),
            ):
                with self.assertRaisesRegex(ValueError, "preflight failed"):
                    runtime.run_once_execute()

            runtime.sync_status.assert_any_call("issue-id-123", "Blocked")


if __name__ == "__main__":
    unittest.main()
