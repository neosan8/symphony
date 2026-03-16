import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from symphony_runtime.executor import run_codex_command


class RunCodexCommandTests(unittest.TestCase):
    def test_run_codex_command_invokes_subprocess_with_expected_contract(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            worktree_path = tmp_path / "worktree"
            worktree_path.mkdir()
            stdout_path = tmp_path / "stdout.log"
            stderr_path = tmp_path / "stderr.log"
            command = ["codex", "exec", "--help"]

            completed_process = MagicMock(returncode=17)

            def fake_run(*args, **kwargs):
                self.assertEqual(args[0], command)
                self.assertEqual(kwargs["cwd"], worktree_path)
                self.assertEqual(Path(kwargs["stdout"].name), stdout_path)
                self.assertEqual(Path(kwargs["stderr"].name), stderr_path)
                self.assertFalse(kwargs["stdout"].closed)
                self.assertFalse(kwargs["stderr"].closed)
                return completed_process

            with patch("subprocess.run", side_effect=fake_run) as mock_run:
                return_code = run_codex_command(
                    command=command,
                    worktree_path=worktree_path,
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                )

            self.assertEqual(return_code, 17)
            mock_run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
