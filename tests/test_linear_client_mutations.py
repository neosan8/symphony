import unittest
from unittest.mock import Mock

from symphony_runtime.linear_client import LinearClient


class LinearClientMutationTests(unittest.TestCase):
    def test_add_comment_posts_graphql_mutation_with_expected_variables(self):
        client = LinearClient(api_key="test-key", team_id="team-123")
        fake_response = Mock()
        fake_response.json.return_value = {"data": {"commentCreate": {"success": True}}}
        fake_response.raise_for_status.return_value = None
        client.session = Mock(post=Mock(return_value=fake_response))

        ok = client.add_comment("issue-id-123", "Hello")

        self.assertTrue(ok)
        kwargs = client.session.post.call_args.kwargs["json"]
        self.assertIn("mutation AddComment", kwargs["query"])
        self.assertIn("commentCreate", kwargs["query"])
        self.assertEqual(
            kwargs["variables"],
            {"issueId": "issue-id-123", "body": "Hello"},
        )

    def test_update_issue_status_posts_graphql_mutation_with_expected_variables(self):
        client = LinearClient(api_key="test-key", team_id="team-123")
        fake_response = Mock()
        fake_response.json.return_value = {"data": {"issueUpdate": {"success": True}}}
        fake_response.raise_for_status.return_value = None
        client.session = Mock(post=Mock(return_value=fake_response))

        ok = client.update_issue_status("issue-id-123", "state-id-456")

        self.assertTrue(ok)
        kwargs = client.session.post.call_args.kwargs["json"]
        self.assertIn("mutation UpdateIssueStatus", kwargs["query"])
        self.assertIn("issueUpdate", kwargs["query"])
        self.assertEqual(
            kwargs["variables"],
            {"issueId": "issue-id-123", "stateId": "state-id-456"},
        )

    def test_add_comment_returns_false_when_mutation_reports_unsuccessful(self):
        client = LinearClient(api_key="test-key", team_id="team-123")
        fake_response = Mock()
        fake_response.json.return_value = {"data": {"commentCreate": {"success": False}}}
        fake_response.raise_for_status.return_value = None
        client.session = Mock(post=Mock(return_value=fake_response))

        ok = client.add_comment("issue-id-123", "Hello")

        self.assertFalse(ok)
