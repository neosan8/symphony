import tempfile
import unittest
from pathlib import Path

from symphony_runtime.executor import build_codex_command


class ExecutorCommandTests(unittest.TestCase):
    def test_build_codex_command_uses_expected_codex_exec_contract(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            worktree_path = Path(tmpdir) / "worktrees" / "issue-123"
            context_packet_path = worktree_path / "artifacts" / "context.md"

            command = build_codex_command(worktree_path, context_packet_path)

            self.assertEqual(
                command,
                [
                    "codex",
                    "exec",
                    "--cwd",
                    str(worktree_path),
                    f"Read {context_packet_path} and complete the issue with verification artifacts.",
                ],
            )
