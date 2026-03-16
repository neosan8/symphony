import unittest

from symphony_runtime.review import pick_review_mode


class ReviewPolicyTests(unittest.TestCase):
    def test_high_risk_uses_codex_and_claude(self):
        self.assertEqual(pick_review_mode("high"), ["codex", "claude"])

    def test_low_risk_uses_codex_only(self):
        self.assertEqual(pick_review_mode("low"), ["codex"])

    def test_unknown_risk_tier_raises_value_error(self):
        with self.assertRaisesRegex(ValueError, "Unsupported risk tier"):
            pick_review_mode("medium")
