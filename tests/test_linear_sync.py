import unittest

from symphony_runtime.linear_sync import build_human_gate_comment


class LinearSyncTests(unittest.TestCase):
    def test_human_gate_comment_renders_exact_decision_surface(self):
        comment = build_human_gate_comment(
            issue_key="LIN-42",
            branch="sym/LIN-42-clean-output",
            commit_sha="abc123",
            recommendation="ready",
            summary="Cleaner output",
            verification="Tests passed",
            review="Codex review passed",
        )
        self.assertEqual(
            comment,
            "\n".join(
                [
                    "Human Gate for LIN-42",
                    "Recommendation: ready",
                    "Branch: sym/LIN-42-clean-output",
                    "Commit: abc123",
                    "",
                    "Summary:",
                    "Cleaner output",
                    "",
                    "Verification:",
                    "Tests passed",
                    "",
                    "Review:",
                    "Codex review passed",
                ]
            ),
        )
