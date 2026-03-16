import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from symphony_runtime.config import SymphonyConfig
from symphony_runtime.daemon import SymphonyRuntime


class RuntimeLinearStatusSyncTests(unittest.TestCase):
    def test_sync_status_resolves_state_name_and_updates_linear_issue(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = SymphonyRuntime(
                config=SymphonyConfig(
                    workspace_root=Path(tmpdir),
                    config_root=Path(tmpdir) / "config",
                    runs_root=Path(tmpdir) / "runs",
                    worktrees_root=Path(tmpdir) / "worktrees",
                )
            )
            runtime.linear_client = Mock()
            runtime.linear_client.fetch_workflow_states.return_value = {
                "In Progress": "state-progress"
            }
            runtime.linear_client.update_issue_status.return_value = True

            ok = runtime.sync_status("issue-id-123", "In Progress")

            self.assertTrue(ok)
            runtime.linear_client.update_issue_status.assert_called_once_with(
                "issue-id-123", "state-progress"
            )

    def test_sync_status_reuses_cached_linear_state_map_across_repeated_syncs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = SymphonyRuntime(
                config=SymphonyConfig(
                    workspace_root=Path(tmpdir),
                    config_root=Path(tmpdir) / "config",
                    runs_root=Path(tmpdir) / "runs",
                    worktrees_root=Path(tmpdir) / "worktrees",
                )
            )
            runtime.linear_client = Mock()
            runtime.linear_client.fetch_workflow_states.return_value = {
                "In Progress": "state-progress"
            }
            runtime.linear_client.update_issue_status.return_value = True

            first_ok = runtime.sync_status("issue-id-123", "In Progress")
            second_ok = runtime.sync_status("issue-id-456", "In Progress")

            self.assertTrue(first_ok)
            self.assertTrue(second_ok)
            runtime.linear_client.fetch_workflow_states.assert_called_once_with()
            self.assertEqual(runtime.linear_client.update_issue_status.call_count, 2)
            runtime.linear_client.update_issue_status.assert_any_call(
                "issue-id-123", "state-progress"
            )
            runtime.linear_client.update_issue_status.assert_any_call(
                "issue-id-456", "state-progress"
            )

    def test_sync_status_returns_false_for_blank_issue_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = SymphonyRuntime(
                config=SymphonyConfig(
                    workspace_root=Path(tmpdir),
                    config_root=Path(tmpdir) / "config",
                    runs_root=Path(tmpdir) / "runs",
                    worktrees_root=Path(tmpdir) / "worktrees",
                )
            )
            runtime.linear_client = Mock()

            ok = runtime.sync_status("", "In Progress")

            self.assertFalse(ok)
            runtime.linear_client.fetch_workflow_states.assert_not_called()
            runtime.linear_client.update_issue_status.assert_not_called()

    def test_sync_status_raises_lookup_error_for_unknown_state_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = SymphonyRuntime(
                config=SymphonyConfig(
                    workspace_root=Path(tmpdir),
                    config_root=Path(tmpdir) / "config",
                    runs_root=Path(tmpdir) / "runs",
                    worktrees_root=Path(tmpdir) / "worktrees",
                )
            )
            runtime.linear_client = Mock()
            runtime.linear_client.fetch_workflow_states.return_value = {
                "In Progress": "state-progress"
            }

            with self.assertRaises(LookupError) as exc:
                runtime.sync_status("issue-id-123", "Done")

            self.assertEqual(str(exc.exception), "Linear workflow state not found: Done")
            runtime.linear_client.fetch_workflow_states.assert_called_once_with()
            runtime.linear_client.update_issue_status.assert_not_called()
