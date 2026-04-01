import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from symphony_runtime.git_handoff import resolve_head_commit


class GitHandoffTests(unittest.TestCase):
    @patch("symphony_runtime.git_handoff.subprocess.run")
    def test_resolve_head_commit_returns_verified_sha(self, run_mock):
        run_mock.return_value.returncode = 0
        run_mock.return_value.stdout = "abc123def456\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            sha = resolve_head_commit(Path(tmpdir))
        self.assertEqual(sha, "abc123def456")

    @patch("symphony_runtime.git_handoff.subprocess.run")
    def test_resolve_head_commit_raises_when_head_cannot_be_resolved(self, run_mock):
        run_mock.return_value.returncode = 128
        run_mock.return_value.stdout = ""
        run_mock.return_value.stderr = "fatal: ambiguous argument 'HEAD'"

        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(RuntimeError, "Could not resolve HEAD"):
                resolve_head_commit(Path(tmpdir))


if __name__ == "__main__":
    unittest.main()
