import unittest

from symphony_runtime.linear_sync import build_started_comment, build_blocked_comment


class LinearSyncRuntimeTests(unittest.TestCase):
    def test_build_started_comment_returns_exact_contract(self):
        self.assertEqual(
            build_started_comment("LIN-42", "feature/lin-42"),
            "Execution started for LIN-42\nBranch: feature/lin-42",
        )

    def test_build_blocked_comment_returns_exact_contract(self):
        self.assertEqual(
            build_blocked_comment("LIN-42", "base branch missing"),
            "Execution blocked for LIN-42\nReason: base branch missing",
        )
