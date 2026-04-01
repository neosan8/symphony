import json
import unittest

from symphony_runtime.review_triage import ReviewFinding, summarize_review_payload


class ReviewTriageTests(unittest.TestCase):
    def test_summarize_review_payload_preserves_non_empty_comment_and_review_bodies(self):
        payload = json.dumps(
            {
                "comments": [
                    {
                        "id": "c1",
                        "body": "Rename this helper",
                        "author": {"login": "reviewer"},
                    },
                    {
                        "id": "c2",
                        "body": "Looks good",
                        "author": {"login": "reviewer"},
                    },
                ],
                "reviews": [
                    {
                        "id": "r1",
                        "body": "Blocking until naming is fixed",
                        "state": "CHANGES_REQUESTED",
                        "author": {"login": "reviewer"},
                    }
                ],
            }
        )

        summary = summarize_review_payload(payload)

        self.assertEqual(summary.total_findings, 3)
        self.assertEqual(summary.blocking_count, 1)
        self.assertEqual(
            [finding.body for finding in summary.unresolved_findings],
            [
                "Rename this helper",
                "Looks good",
                "Blocking until naming is fixed",
            ],
        )

    def test_summarize_review_payload_counts_empty_changes_requested_review_as_blocking(self):
        payload = json.dumps(
            {
                "reviews": [
                    {
                        "id": "r1",
                        "body": "",
                        "state": "CHANGES_REQUESTED",
                        "author": {"login": "reviewer"},
                    },
                    {
                        "id": "r2",
                        "body": None,
                        "state": "APPROVED",
                        "author": {"login": "reviewer"},
                    },
                ]
            }
        )

        summary = summarize_review_payload(payload)

        self.assertEqual(summary.total_findings, 0)
        self.assertEqual(summary.blocking_count, 1)
        self.assertEqual(summary.unresolved_findings, [])

    def test_summarize_review_payload_ignores_whitespace_only_bodies(self):
        payload = json.dumps(
            {
                "comments": [
                    {
                        "id": "c1",
                        "body": "   \n\t  ",
                        "author": {"login": "reviewer"},
                    }
                ],
                "reviews": [
                    {
                        "id": "r1",
                        "body": "\n  \t",
                        "state": "COMMENTED",
                        "author": {"login": "reviewer"},
                    }
                ],
            }
        )

        summary = summarize_review_payload(payload)

        self.assertEqual(summary.total_findings, 0)
        self.assertEqual(summary.blocking_count, 0)
        self.assertEqual(summary.unresolved_findings, [])

    def test_summarize_review_payload_tolerates_missing_top_level_lists(self):
        summary = summarize_review_payload(json.dumps({}))

        self.assertEqual(summary.total_findings, 0)
        self.assertEqual(summary.blocking_count, 0)
        self.assertEqual(summary.unresolved_findings, [])

    def test_summarize_review_payload_preserves_blocking_flag_on_emitted_review_findings(self):
        payload = json.dumps(
            {
                "reviews": [
                    {
                        "id": "r1",
                        "body": "Please address this before merge",
                        "state": "CHANGES_REQUESTED",
                        "author": {"login": "reviewer"},
                    }
                ]
            }
        )

        summary = summarize_review_payload(payload)

        self.assertEqual(
            summary.unresolved_findings,
            [
                ReviewFinding(
                    source="review",
                    finding_id="r1",
                    author="reviewer",
                    body="Please address this before merge",
                    is_blocking=True,
                )
            ],
        )
        self.assertEqual(summary.blocking_count, 1)

    def test_summarize_review_payload_rejects_malformed_top_level_payload(self):
        with self.assertRaisesRegex(
            ValueError,
            "review payload must be a JSON object with optional 'comments' and 'reviews' lists",
        ):
            summarize_review_payload(json.dumps([{"id": "c1"}]))

    def test_summarize_review_payload_rejects_malformed_top_level_comments_or_reviews(self):
        for payload in (
            {"comments": "nope"},
            {"reviews": {"id": "r1"}},
        ):
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(
                    ValueError,
                    "review payload must be a JSON object with optional 'comments' and 'reviews' lists",
                ):
                    summarize_review_payload(json.dumps(payload))

    def test_summarize_review_payload_rejects_malformed_comment_or_review_entries(self):
        payload = json.dumps(
            {
                "comments": [None, "bad-comment", 3],
                "reviews": [None, "bad-review", 7],
            }
        )

        with self.assertRaisesRegex(
            ValueError,
            "review payload comments and reviews must contain only JSON objects",
        ):
            summarize_review_payload(payload)


if __name__ == "__main__":
    unittest.main()
