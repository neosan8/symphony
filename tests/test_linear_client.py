import unittest
from typing import get_type_hints

from symphony_runtime.linear_client import LinearClient
from symphony_runtime.models import LinearIssue


class LinearClientTypingTests(unittest.TestCase):
    def test_fetch_candidate_issues_returns_typed_linear_issues(self):
        hints = get_type_hints(LinearClient.fetch_candidate_issues)

        self.assertEqual(hints["return"], list[LinearIssue])


if __name__ == "__main__":
    unittest.main()
