import unittest
from unittest.mock import Mock

from symphony_runtime.linear_client import LinearClient


class LinearClientFetchTests(unittest.TestCase):
    def test_fetch_candidate_issues_maps_graphql_response_to_linear_issues(self):
        client = LinearClient(api_key="test-key", team_id="team-123")
        fake_response = Mock()
        fake_response.json.return_value = {
            "data": {
                "issues": {
                    "nodes": [
                        {
                            "id": "issue-id-123",
                            "identifier": "LIN-42",
                            "title": "Fix output",
                            "description": "Make Human Gate cleaner",
                            "state": {"name": "Todo"},
                            "project": {"key": "symphony"},
                            "labels": {"nodes": [{"name": "agent-ready"}]},
                        }
                    ]
                }
            }
        }
        fake_response.raise_for_status.return_value = None
        client.session = Mock(post=Mock(return_value=fake_response))

        issues = client.fetch_candidate_issues()

        client.session.post.assert_called_once()
        _, kwargs = client.session.post.call_args
        self.assertEqual(kwargs["json"]["variables"], {"teamId": "team-123"})
        self.assertIn("query CandidateIssues", kwargs["json"]["query"])
        self.assertIn("issues(filter:", kwargs["json"]["query"])
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].id, "issue-id-123")
        self.assertEqual(issues[0].identifier, "LIN-42")
        self.assertEqual(issues[0].status, "Todo")
        self.assertEqual(issues[0].project_key, "symphony")
        self.assertEqual(issues[0].labels, ["agent-ready"])

    def test_fetch_candidate_issues_raises_when_graphql_errors_present_even_with_nodes(self):
        client = LinearClient(api_key="test-key", team_id="team-123")
        fake_response = Mock()
        fake_response.json.return_value = {
            "errors": [{"message": "Partial failure"}],
            "data": {
                "issues": {
                    "nodes": [
                        {
                            "id": "issue-id-123",
                            "identifier": "LIN-42",
                            "title": "Fix output",
                            "description": "Make Human Gate cleaner",
                            "state": {"name": "Todo"},
                            "project": {"key": "symphony"},
                            "labels": {"nodes": [{"name": "agent-ready"}]},
                        }
                    ]
                }
            },
        }
        fake_response.raise_for_status.return_value = None
        client.session = Mock(post=Mock(return_value=fake_response))

        with self.assertRaisesRegex(ValueError, "Partial failure"):
            client.fetch_candidate_issues()

    def test_fetch_candidate_issues_handles_nullable_optional_graphql_fields(self):
        client = LinearClient(api_key="test-key", team_id="team-123")
        fake_response = Mock()
        fake_response.json.return_value = {
            "data": {
                "issues": {
                    "nodes": [
                        {
                            "id": "issue-id-999",
                            "identifier": "LIN-99",
                            "title": "Handle nulls",
                            "description": None,
                            "state": {"name": "Todo"},
                            "project": None,
                            "labels": None,
                        }
                    ]
                }
            }
        }
        fake_response.raise_for_status.return_value = None
        client.session = Mock(post=Mock(return_value=fake_response))

        issues = client.fetch_candidate_issues()

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].id, "issue-id-999")
        self.assertEqual(issues[0].identifier, "LIN-99")
        self.assertEqual(issues[0].description, "")
        self.assertEqual(issues[0].status, "Todo")
        self.assertEqual(issues[0].project_key, "")
        self.assertEqual(issues[0].labels, [])

    def test_fetch_candidate_issues_raises_when_required_id_missing(self):
        client = LinearClient(api_key="test-key", team_id="team-123")
        fake_response = Mock()
        fake_response.json.return_value = {
            "data": {
                "issues": {
                    "nodes": [
                        {
                            "id": "",
                            "identifier": "LIN-99",
                            "title": "Handle nulls",
                            "description": None,
                            "state": {"name": "Todo"},
                            "project": None,
                            "labels": None,
                        }
                    ]
                }
            }
        }
        fake_response.raise_for_status.return_value = None
        client.session = Mock(post=Mock(return_value=fake_response))

        with self.assertRaisesRegex(ValueError, "missing required field: id"):
            client.fetch_candidate_issues()

    def test_fetch_candidate_issues_raises_when_required_state_name_missing(self):
        client = LinearClient(api_key="test-key", team_id="team-123")
        fake_response = Mock()
        fake_response.json.return_value = {
            "data": {
                "issues": {
                    "nodes": [
                        {
                            "id": "issue-id-999",
                            "identifier": "LIN-99",
                            "title": "Handle nulls",
                            "description": None,
                            "state": None,
                            "project": None,
                            "labels": None,
                        }
                    ]
                }
            }
        }
        fake_response.raise_for_status.return_value = None
        client.session = Mock(post=Mock(return_value=fake_response))

        with self.assertRaisesRegex(ValueError, "missing required field: state.name"):
            client.fetch_candidate_issues()


if __name__ == "__main__":
    unittest.main()
