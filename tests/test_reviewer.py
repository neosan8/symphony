import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from symphony_runtime.models import ReviewerResult
from symphony_runtime.reviewer import (
    build_reviewer_command,
    run_reviewer,
    _parse_reviewer_output,
)


class TestParseReviewerOutput(unittest.TestCase):
    def test_approved_response(self):
        approved, findings = _parse_reviewer_output("APPROVED")
        self.assertTrue(approved)
        self.assertEqual(findings, [])

    def test_approved_with_trailing_whitespace(self):
        approved, findings = _parse_reviewer_output("APPROVED\n\n")
        self.assertTrue(approved)
        self.assertEqual(findings, [])

    def test_blocking_response_single(self):
        approved, findings = _parse_reviewer_output("BLOCKING: Missing null check in handler")
        self.assertFalse(approved)
        self.assertEqual(findings, ["Missing null check in handler"])

    def test_blocking_response_multiple(self):
        raw = (
            "BLOCKING: Missing null check\n"
            "BLOCKING: SQL injection risk in query builder\n"
            "BLOCKING: Tests not updated\n"
        )
        approved, findings = _parse_reviewer_output(raw)
        self.assertFalse(approved)
        self.assertEqual(len(findings), 3)
        self.assertIn("Missing null check", findings)
        self.assertIn("SQL injection risk in query builder", findings)
        self.assertIn("Tests not updated", findings)

    def test_empty_output_is_approved(self):
        approved, findings = _parse_reviewer_output("")
        self.assertTrue(approved)
        self.assertEqual(findings, [])

    def test_approved_in_mixed_text(self):
        approved, findings = _parse_reviewer_output("Looks good overall. APPROVED")
        self.assertTrue(approved)
        self.assertEqual(findings, [])


class TestBuildReviewerCommand(unittest.TestCase):
    def test_builds_claude_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            worktree = Path(tmpdir) / "worktree"
            worktree.mkdir()
            context = Path(tmpdir) / "context.md"
            context.write_text("# TEST-1: Fix bug\n\n## Description\nFix the bug\n")
            cmd = build_reviewer_command(worktree, context, "1 file changed", model="claude-sonnet-4-20250514")
            self.assertEqual(cmd[0], "claude")
            self.assertEqual(cmd[1], "-p")
            self.assertIn("--model", cmd)
            self.assertIn("claude-sonnet-4-20250514", cmd)
            self.assertIn("code reviewer", cmd[2])

    def test_includes_diff_summary_in_prompt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            worktree = Path(tmpdir) / "worktree"
            worktree.mkdir()
            context = Path(tmpdir) / "context.md"
            context.write_text("# TEST-1\n")
            cmd = build_reviewer_command(worktree, context, "3 files changed")
            self.assertIn("3 files changed", cmd[2])


class TestRunReviewer(unittest.TestCase):
    def test_approved_subprocess(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            worktree = Path(tmpdir) / "worktree"
            worktree.mkdir()
            context = Path(tmpdir) / "context.md"
            context.write_text("# TEST-1\n")
            stdout_path = Path(tmpdir) / "reviewer_1.log"
            stderr_path = Path(tmpdir) / "reviewer_1_err.log"

            call_count = {"n": 0}
            def fake_run(command, **kwargs):
                call_count["n"] += 1
                if call_count["n"] == 1:
                    # git diff call
                    mock_result = MagicMock()
                    mock_result.returncode = 1
                    mock_result.stdout = ""
                    return mock_result
                # claude call
                stdout = kwargs.get("stdout")
                if stdout:
                    stdout.write("APPROVED")
                mock_result = MagicMock()
                mock_result.returncode = 0
                return mock_result

            with patch("symphony_runtime.reviewer.subprocess.run", side_effect=fake_run):
                result = run_reviewer(worktree, context, stdout_path, stderr_path)

            self.assertIsInstance(result, ReviewerResult)
            self.assertTrue(result.approved)
            self.assertEqual(result.findings, [])

    def test_blocking_subprocess(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            worktree = Path(tmpdir) / "worktree"
            worktree.mkdir()
            context = Path(tmpdir) / "context.md"
            context.write_text("# TEST-1\n")
            stdout_path = Path(tmpdir) / "reviewer_1.log"
            stderr_path = Path(tmpdir) / "reviewer_1_err.log"

            call_count = {"n": 0}
            def fake_run(command, **kwargs):
                call_count["n"] += 1
                if call_count["n"] == 1:
                    # git diff call
                    mock_result = MagicMock()
                    mock_result.returncode = 1
                    mock_result.stdout = ""
                    return mock_result
                # claude call
                stdout = kwargs.get("stdout")
                if stdout:
                    stdout.write("BLOCKING: Missing error handling\nBLOCKING: No tests\n")
                mock_result = MagicMock()
                mock_result.returncode = 0
                return mock_result

            with patch("symphony_runtime.reviewer.subprocess.run", side_effect=fake_run):
                result = run_reviewer(worktree, context, stdout_path, stderr_path)

            self.assertIsInstance(result, ReviewerResult)
            self.assertFalse(result.approved)
            self.assertEqual(len(result.findings), 2)
            self.assertIn("Missing error handling", result.findings)
            self.assertIn("No tests", result.findings)

    def test_fail_open_on_nonzero_exit(self):
        """If claude exits with non-zero code, reviewer should fail-open (approved=True)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            worktree = Path(tmpdir) / "worktree"
            worktree.mkdir()
            context = Path(tmpdir) / "context.md"
            context.write_text("# TEST-1\n")
            stdout_path = Path(tmpdir) / "reviewer_1.log"
            stderr_path = Path(tmpdir) / "reviewer_1_err.log"

            call_count = {"n": 0}
            def fake_run(command, **kwargs):
                call_count["n"] += 1
                if call_count["n"] == 1:
                    mock_result = MagicMock()
                    mock_result.returncode = 1
                    mock_result.stdout = ""
                    return mock_result
                mock_result = MagicMock()
                mock_result.returncode = 1
                return mock_result

            with patch("symphony_runtime.reviewer.subprocess.run", side_effect=fake_run):
                result = run_reviewer(worktree, context, stdout_path, stderr_path)

            self.assertTrue(result.approved)
            self.assertEqual(result.findings, [])

    def test_fail_open_on_timeout(self):
        """If claude times out, reviewer should fail-open."""
        import subprocess as real_subprocess
        with tempfile.TemporaryDirectory() as tmpdir:
            worktree = Path(tmpdir) / "worktree"
            worktree.mkdir()
            context = Path(tmpdir) / "context.md"
            context.write_text("# TEST-1\n")
            stdout_path = Path(tmpdir) / "reviewer_1.log"
            stderr_path = Path(tmpdir) / "reviewer_1_err.log"

            def fake_run(*args, **kwargs):
                raise real_subprocess.TimeoutExpired(cmd="claude", timeout=300)

            with patch("symphony_runtime.reviewer.subprocess.run", side_effect=fake_run):
                result = run_reviewer(worktree, context, stdout_path, stderr_path)

            self.assertTrue(result.approved)
            self.assertEqual(result.findings, [])


class TestReviewerResult(unittest.TestCase):
    def test_dataclass_fields(self):
        r = ReviewerResult(approved=True, findings=[], raw_output="APPROVED", iterations=1)
        self.assertTrue(r.approved)
        self.assertEqual(r.findings, [])
        self.assertEqual(r.raw_output, "APPROVED")
        self.assertEqual(r.iterations, 1)


if __name__ == "__main__":
    unittest.main()
