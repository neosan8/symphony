import unittest

from symphony_runtime.models import LinearIssue


class LinearIssueModelTests(unittest.TestCase):
    def test_linear_issue_requires_core_identity_and_state_fields(self):
        with self.assertRaises(TypeError):
            LinearIssue(
                identifier="LIN-42",
                title="Fix output",
                status="Todo",
            )

    def test_linear_issue_rejects_empty_required_core_fields(self):
        with self.assertRaisesRegex(ValueError, "LinearIssue.id must be a non-empty string"):
            LinearIssue(
                id="",
                identifier="LIN-42",
                title="Fix output",
                status="Todo",
            )

    def test_linear_issue_allows_optional_text_and_collection_fields(self):
        issue = LinearIssue(
            id="issue-id-123",
            identifier="LIN-42",
            title="Fix output",
            status="Todo",
        )

        self.assertEqual(issue.description, "")
        self.assertEqual(issue.project_key, "")
        self.assertEqual(issue.labels, [])
        self.assertEqual(issue.comments, [])
        self.assertEqual(issue.links, [])


if __name__ == "__main__":
    unittest.main()
