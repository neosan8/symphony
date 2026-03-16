import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from symphony_runtime.config import SymphonyConfig
from symphony_runtime.daemon import SymphonyRuntime
from symphony_runtime.models import ExecutionResult


class RuntimeExecuteTests(unittest.TestCase):
    @patch("symphony_runtime.daemon.run_codex_command", return_value=0)
    def test_execute_prepared_run_creates_logs_and_calls_executor_with_expected_args(
        self, run_codex_command_mock
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = SymphonyRuntime(
                config=SymphonyConfig(
                    workspace_root=Path(tmpdir),
                    config_root=Path(tmpdir) / "config",
                    runs_root=Path(tmpdir) / "runs",
                    worktrees_root=Path(tmpdir) / "worktrees",
                )
            )
            run_root = Path(tmpdir) / "runs" / "lin-42"
            worktree_path = Path(tmpdir) / "worktrees" / "lin-42"
            command = ["codex", "exec"]
            run_root.mkdir(parents=True)
            worktree_path.mkdir(parents=True)

            result = runtime.execute_prepared_run(
                issue_key="LIN-42",
                run_root=run_root,
                worktree_path=worktree_path,
                branch_name="feature/lin-42",
                command=command,
                preflight_ok=True,
            )

            stdout_path = run_root / "logs" / "stdout.log"
            stderr_path = run_root / "logs" / "stderr.log"

            self.assertIsInstance(result, ExecutionResult)
            self.assertEqual(result.return_code, 0)
            self.assertEqual(result.command, tuple(command))
            self.assertEqual(result.stdout_path, stdout_path)
            self.assertEqual(result.stderr_path, stderr_path)
            self.assertTrue(stdout_path.exists())
            self.assertTrue(stderr_path.exists())
            run_codex_command_mock.assert_called_once_with(
                command=command,
                worktree_path=worktree_path,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
            )

    @patch("symphony_runtime.daemon.run_codex_command")
    def test_execute_prepared_run_raises_when_preflight_failed(self, run_codex_command_mock):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = SymphonyRuntime(
                config=SymphonyConfig(
                    workspace_root=Path(tmpdir),
                    config_root=Path(tmpdir) / "config",
                    runs_root=Path(tmpdir) / "runs",
                    worktrees_root=Path(tmpdir) / "worktrees",
                )
            )
            run_root = Path(tmpdir) / "runs" / "lin-42"
            worktree_path = Path(tmpdir) / "worktrees" / "lin-42"
            run_root.mkdir(parents=True)
            worktree_path.mkdir(parents=True)

            with self.assertRaisesRegex(ValueError, "preflight"):
                runtime.execute_prepared_run(
                    issue_key="LIN-42",
                    run_root=run_root,
                    worktree_path=worktree_path,
                    branch_name="feature/lin-42",
                    command=["codex", "exec"],
                    preflight_ok=False,
                )

            self.assertFalse((run_root / "logs").exists())
            run_codex_command_mock.assert_not_called()
