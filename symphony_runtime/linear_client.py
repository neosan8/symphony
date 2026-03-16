from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import LinearIssue


@dataclass
class LinearClient:
    api_key: str
    team_id: str
    api_url: str = "https://api.linear.app/graphql"
    session: Any | None = field(default=None, init=False, repr=False)

    def _build_session(self) -> Any:
        import requests  # type: ignore

        session = requests.Session()
        session.headers.update(
            {
                "Authorization": self.api_key,
                "Content-Type": "application/json",
            }
        )
        return session

    def _post_graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        if self.session is None:
            self.session = self._build_session()

        response = self.session.post(
            self.api_url,
            json={"query": query, "variables": variables},
        )
        response.raise_for_status()
        payload = response.json()
        errors = payload.get("errors") or []
        if errors:
            message = errors[0].get("message", "GraphQL request failed")
            raise ValueError(message)
        return payload.get("data") or {}

    def _require_issue_field(self, node: dict[str, Any], field_name: str) -> str:
        value = node.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Linear issue payload missing required field: {field_name}")
        return value

    def _require_issue_status(self, node: dict[str, Any]) -> str:
        state = node.get("state")
        status = state.get("name") if isinstance(state, dict) else None
        if not isinstance(status, str) or not status.strip():
            raise ValueError("Linear issue payload missing required field: state.name")
        return status

    def _require_state_field(self, node: dict[str, Any], field_name: str) -> str:
        value = node.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Linear state payload missing required field: {field_name}")
        return value

    def _require_workflow_state_nodes(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        team = data.get("team")
        if not isinstance(team, dict):
            raise ValueError("Linear workflow states payload missing required shape: team.states.nodes")

        states = team.get("states")
        if not isinstance(states, dict):
            raise ValueError("Linear workflow states payload missing required shape: team.states.nodes")

        nodes = states.get("nodes")
        if not isinstance(nodes, list):
            raise ValueError("Linear workflow states payload missing required shape: team.states.nodes")

        return nodes

    def fetch_workflow_states(self) -> dict[str, str]:
        query = """
        query TeamWorkflowStates($teamId: String!) {
          team(id: $teamId) {
            states {
              nodes {
                id
                name
              }
            }
          }
        }
        """
        data = self._post_graphql(query, {"teamId": self.team_id})
        nodes = self._require_workflow_state_nodes(data)

        return {
            self._require_state_field(node, "name"): self._require_state_field(node, "id")
            for node in nodes
        }

    def fetch_candidate_issues(self) -> list[LinearIssue]:
        query = """
        query CandidateIssues($teamId: String!) {
          issues(filter: { team: { id: { eq: $teamId } } }) {
            nodes {
              id
              identifier
              title
              description
              state {
                name
              }
              project {
                key
              }
              labels {
                nodes {
                  name
                }
              }
            }
          }
        }
        """
        data = self._post_graphql(query, {"teamId": self.team_id})
        issues = data.get("issues") or {}
        nodes = issues.get("nodes") or []

        return [
            LinearIssue(
                id=self._require_issue_field(node, "id"),
                identifier=self._require_issue_field(node, "identifier"),
                title=self._require_issue_field(node, "title"),
                description=node.get("description") or "",
                status=self._require_issue_status(node),
                project_key=((node.get("project") or {}).get("key") or ""),
                labels=[label["name"] for label in ((node.get("labels") or {}).get("nodes") or [])],
            )
            for node in nodes
        ]

    def add_comment(self, issue_id: str, body: str) -> bool:
        query = """
        mutation AddComment($issueId: String!, $body: String!) {
          commentCreate(input: { issueId: $issueId, body: $body }) {
            success
          }
        }
        """
        data = self._post_graphql(query, {"issueId": issue_id, "body": body})
        return bool(((data.get("commentCreate") or {}).get("success")))

    def update_issue_status(self, issue_id: str, state_id: str) -> bool:
        query = """
        mutation UpdateIssueStatus($issueId: String!, $stateId: String!) {
          issueUpdate(id: $issueId, input: { stateId: $stateId }) {
            success
          }
        }
        """
        data = self._post_graphql(query, {"issueId": issue_id, "stateId": state_id})
        return bool(((data.get("issueUpdate") or {}).get("success")))
