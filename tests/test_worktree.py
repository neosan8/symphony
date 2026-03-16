import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from symphony_runtime.worktree import ensure_issue_worktree


class EnsureIssueWorktreeTests(unittest.TestCase):
    def test_returns_without_running_git_when_existing_path_looks_like_worktree(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir) / "repo"
            worktree_path = Path(tmpdir) / "worktrees" / "SYM-001"
            repo_path.mkdir()
            worktree_path.mkdir(parents=True)
            (worktree_path / ".git").write_text("gitdir: /tmp/fake")

            with patch("symphony_runtime.worktree.subprocess.run") as run_mock:
                ensure_issue_worktree(repo_path, worktree_path, "feature/SYM-001", "main")

            run_mock.assert_not_called()

    def test_raises_when_existing_path_does_not_look_like_worktree(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir) / "repo"
            worktree_path = Path(tmpdir) / "worktrees" / "SYM-001"
            repo_path.mkdir()
            worktree_path.mkdir(parents=True)

            with patch("symphony_runtime.worktree.subprocess.run") as run_mock:
                with self.assertRaisesRegex(ValueError, "Existing path is not a git worktree"):
                    ensure_issue_worktree(repo_path, worktree_path, "feature/SYM-001", "main")

            run_mock.assert_not_called()

    def test_creates_worktree_when_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir) / "repo"
            worktree_path = Path(tmpdir) / "worktrees" / "SYM-001"
            repo_path.mkdir()

            with patch("symphony_runtime.worktree.subprocess.run") as run_mock:
                ensure_issue_worktree(repo_path, worktree_path, "feature/SYM-001", "main")

            self.assertTrue(worktree_path.parent.exists())
            run_mock.assert_called_once_with(
                ["git", "worktree", "add", str(worktree_path), "-b", "feature/SYM-001", "main"],
                cwd=repo_path,
                check=True,
            )


if __name__ == "__main__":
    unittest.main()
