import unittest
from unittest.mock import Mock

from symphony_runtime.linear_client import LinearClient


class LinearClientStateTests(unittest.TestCase):
    def _build_client_with_payload(self, payload):
        client = LinearClient(api_key="test-key", team_id="team-123")
        fake_response = Mock()
        fake_response.json.return_value = payload
        fake_response.raise_for_status.return_value = None
        client.session = Mock(post=Mock(return_value=fake_response))
        return client

    def test_fetch_workflow_states_returns_name_to_id_map(self):
        client = self._build_client_with_payload(
            {
                "data": {
                    "team": {
                        "states": {
                            "nodes": [
                                {"id": "state-todo", "name": "Todo"},
                                {"id": "state-progress", "name": "In Progress"},
                                {"id": "state-blocked", "name": "Blocked"},
                                {"id": "state-done", "name": "Done"},
                            ]
                        }
                    }
                }
            }
        )

        states = client.fetch_workflow_states()

        self.assertEqual(states["Todo"], "state-todo")
        self.assertEqual(states["In Progress"], "state-progress")
        self.assertEqual(states["Blocked"], "state-blocked")
        self.assertEqual(states["Done"], "state-done")

    def test_fetch_workflow_states_raises_for_missing_payload_shape(self):
        client = self._build_client_with_payload({"data": {"team": {}}})

        with self.assertRaisesRegex(
            ValueError,
            "Linear workflow states payload missing required shape: team.states.nodes",
        ):
            client.fetch_workflow_states()

    def test_fetch_workflow_states_raises_for_blank_state_fields(self):
        client = self._build_client_with_payload(
            {
                "data": {
                    "team": {
                        "states": {
                            "nodes": [
                                {"id": "state-todo", "name": "Todo"},
                                {"id": " ", "name": "Blocked"},
                            ]
                        }
                    }
                }
            }
        )

        with self.assertRaisesRegex(
            ValueError,
            "Linear state payload missing required field: id",
        ):
            client.fetch_workflow_states()
