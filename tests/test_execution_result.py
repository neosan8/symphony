import unittest
from pathlib import Path

from symphony_runtime.models import ExecutionResult


class ExecutionResultTests(unittest.TestCase):
    def test_execution_result_captures_core_runtime_outputs(self):
        result = ExecutionResult(
            issue_key="LIN-42",
            run_root=Path("/tmp/run"),
            worktree_path=Path("/tmp/worktree"),
            branch_name="feature/lin-42",
            command=("codex", "exec"),
            return_code=0,
            stdout_path=Path("/tmp/run/logs/stdout.log"),
            stderr_path=Path("/tmp/run/logs/stderr.log"),
            preflight_ok=True,
        )
        self.assertEqual(result.issue_key, "LIN-42")
        self.assertEqual(result.return_code, 0)
        self.assertEqual(result.command[0], "codex")
