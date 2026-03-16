import unittest

from symphony_runtime.dispatch import is_issue_dispatchable
from symphony_runtime.models import LinearIssue


class DispatchEligibilityTests(unittest.TestCase):
    def test_issue_requires_dispatch_label(self):
        issue = LinearIssue(
            id="issue-id-42",
            identifier="LIN-42",
            title="Test",
            description="Body",
            status="Todo",
            labels=["agent-ready"],
            project_key="symphony",
            comments=[],
            links=[],
        )
        self.assertTrue(is_issue_dispatchable(issue))

    def test_issue_with_symphony_label_is_dispatchable(self):
        issue = LinearIssue(
            id="issue-id-43",
            identifier="LIN-43",
            title="Test",
            description="Body",
            status="Todo",
            labels=["symphony"],
            project_key="symphony",
            comments=[],
            links=[],
        )
        self.assertTrue(is_issue_dispatchable(issue))

    def test_issue_without_dispatch_label_is_not_dispatchable(self):
        issue = LinearIssue(
            id="issue-id-44",
            identifier="LIN-44",
            title="Test",
            description="Body",
            status="Todo",
            labels=[],
            project_key="symphony",
            comments=[],
            links=[],
        )
        self.assertFalse(is_issue_dispatchable(issue))

    def test_issue_with_non_todo_status_is_not_dispatchable(self):
        issue = LinearIssue(
            id="issue-id-45",
            identifier="LIN-45",
            title="Test",
            description="Body",
            status="In Progress",
            labels=["agent-ready"],
            project_key="symphony",
            comments=[],
            links=[],
        )
        self.assertFalse(is_issue_dispatchable(issue))
