import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from symphony_runtime.pr_reviews import fetch_pr_review_comments


class PrReviewTests(unittest.TestCase):
    def test_fetch_pr_review_comments_documents_runtime_assumptions(self):
        docstring = fetch_pr_review_comments.__doc__

        self.assertIsNotNone(docstring)
        self.assertIn('gh CLI must be installed', docstring)
        self.assertIn('authenticated', docstring)
        self.assertIn('valid GitHub pull request URL', docstring)

    @patch("symphony_runtime.pr_reviews.subprocess.run")
    def test_fetch_pr_review_comments_returns_json_text(self, run_mock):
        run_mock.return_value.returncode = 0
        run_mock.return_value.stdout = '[{"body":"Please rename this"}]\n'
        run_mock.return_value.stderr = ''

        with tempfile.TemporaryDirectory() as tmpdir:
            output = fetch_pr_review_comments("https://github.com/o/r/pull/42", Path(tmpdir))

        self.assertEqual(output, '[{"body":"Please rename this"}]')
        run_mock.assert_called_once_with(
            [
                'gh',
                'pr',
                'view',
                'https://github.com/o/r/pull/42',
                '--comments',
                '--json',
                'comments,reviews',
            ],
            cwd=Path(tmpdir),
            capture_output=True,
            text=True,
        )

    @patch("symphony_runtime.pr_reviews.subprocess.run")
    def test_fetch_pr_review_comments_rejects_command_failure(self, run_mock):
        run_mock.return_value.returncode = 1
        run_mock.return_value.stdout = ''
        run_mock.return_value.stderr = 'gh auth required\n'

        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(RuntimeError, 'gh auth required'):
                fetch_pr_review_comments("https://github.com/o/r/pull/42", Path(tmpdir))

    @patch("symphony_runtime.pr_reviews.subprocess.run")
    def test_fetch_pr_review_comments_fails_fast_on_empty_output(self, run_mock):
        run_mock.return_value.returncode = 0
        run_mock.return_value.stdout = '   \n'
        run_mock.return_value.stderr = ''

        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(RuntimeError, 'gh returned empty output'):
                fetch_pr_review_comments("https://github.com/o/r/pull/42", Path(tmpdir))
