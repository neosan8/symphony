import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch

from symphony_runtime.pr_create import create_pull_request, ensure_ready_for_pr


class PrCreateTests(unittest.TestCase):
    @patch("symphony_runtime.pr_create.subprocess.run")
    def test_ensure_ready_for_pr_uses_exact_git_commands_and_cwd(self, run_mock):
        run_mock.side_effect = [
            type("R", (), {"returncode": 0, "stdout": "abc123\n", "stderr": ""})(),
            type("R", (), {"returncode": 0, "stdout": "feature/lin-42\n", "stderr": ""})(),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            worktree_path = Path(tmpdir)
            ensure_ready_for_pr(worktree_path, expected_commit="abc123", expected_branch="feature/lin-42")

        self.assertEqual(
            run_mock.call_args_list,
            [
                call(
                    ["git", "rev-parse", "--verify", "HEAD"],
                    cwd=worktree_path,
                    capture_output=True,
                    text=True,
                ),
                call(
                    ["git", "branch", "--show-current"],
                    cwd=worktree_path,
                    capture_output=True,
                    text=True,
                ),
            ],
        )

    @patch("symphony_runtime.pr_create.subprocess.run")
    def test_ensure_ready_for_pr_raises_when_head_does_not_match(self, run_mock):
        run_mock.side_effect = [
            type("R", (), {"returncode": 0, "stdout": "def456\n", "stderr": ""})(),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(RuntimeError, "Expected HEAD abc123, found def456"):
                ensure_ready_for_pr(Path(tmpdir), expected_commit="abc123", expected_branch="feature/lin-42")

    @patch("symphony_runtime.pr_create.subprocess.run")
    def test_ensure_ready_for_pr_raises_when_branch_does_not_match(self, run_mock):
        run_mock.side_effect = [
            type("R", (), {"returncode": 0, "stdout": "abc123\n", "stderr": ""})(),
            type("R", (), {"returncode": 0, "stdout": "main\n", "stderr": ""})(),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(RuntimeError, "Expected branch feature/lin-42, found main"):
                ensure_ready_for_pr(Path(tmpdir), expected_commit="abc123", expected_branch="feature/lin-42")

    @patch("symphony_runtime.pr_create.subprocess.run")
    def test_create_pull_request_uses_exact_push_and_gh_commands_and_returns_pr_url(self, run_mock):
        run_mock.side_effect = [
            type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
            type("R", (), {"returncode": 0, "stdout": "https://github.com/o/r/pull/42\n", "stderr": ""})(),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            worktree_path = Path(tmpdir)
            body_path = worktree_path / "pr_handoff.md"
            url = create_pull_request(
                worktree_path=worktree_path,
                base_branch="main",
                head_branch="feature/lin-42",
                title="LIN-42: Ship it",
                body_path=body_path,
            )

        self.assertEqual(url, "https://github.com/o/r/pull/42")
        self.assertEqual(
            run_mock.call_args_list,
            [
                call(
                    ["git", "push", "-u", "origin", "feature/lin-42"],
                    cwd=worktree_path,
                    capture_output=True,
                    text=True,
                ),
                call(
                    [
                        "gh",
                        "pr",
                        "create",
                        "--base",
                        "main",
                        "--head",
                        "feature/lin-42",
                        "--title",
                        "LIN-42: Ship it",
                        "--body-file",
                        str(body_path),
                    ],
                    cwd=worktree_path,
                    capture_output=True,
                    text=True,
                ),
            ],
        )

    @patch("symphony_runtime.pr_create.subprocess.run")
    def test_create_pull_request_raises_when_gh_returns_empty_stdout(self, run_mock):
        run_mock.side_effect = [
            type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
            type("R", (), {"returncode": 0, "stdout": "\n", "stderr": ""})(),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(RuntimeError, "Failed to create pull request with gh"):
                create_pull_request(
                    worktree_path=Path(tmpdir),
                    base_branch="main",
                    head_branch="feature/lin-42",
                    title="LIN-42: Ship it",
                    body_path=Path(tmpdir) / "pr_handoff.md",
                )
