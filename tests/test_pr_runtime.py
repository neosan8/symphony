import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from symphony_runtime.config import SymphonyConfig
from symphony_runtime.daemon import SymphonyRuntime
from symphony_runtime.run_store import (
    write_human_gate_preview_state,
    write_pr_opened,
    write_pr_review_acknowledgement,
    write_pr_review_snapshot,
    write_summary_artifacts,
)


VALID_ACKNOWLEDGEMENT_STATES = ("reviewed", "addressed", "needs-follow-up")


class PrRuntimeTests(unittest.TestCase):
    def _make_runtime_and_run_root(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        runtime = SymphonyRuntime(
            config=SymphonyConfig(
                workspace_root=Path(tmpdir.name),
                config_root=Path(tmpdir.name) / "config",
                runs_root=Path(tmpdir.name) / "runs",
                worktrees_root=Path(tmpdir.name) / "worktrees",
            )
        )
        run_root = runtime.config.runs_root / "lin-42"
        run_root.mkdir(parents=True)
        (run_root / "status.json").write_text(
            """{
              \"status\": \"done\",
              \"issue_id\": \"issue-id-123\",
              \"issue_key\": \"LIN-42\",
              \"branch\": \"feature/lin-42\",
              \"commit_sha\": \"abc123\",
              \"worktree_path\": \"/tmp/worktree\",
              \"base_branch\": \"main\",
              \"human_gate\": {
                \"decision\": \"approve\",
                \"note\": \"Ship it\",
                \"decision_required\": false,
                \"decision_applied\": true,
                \"applied_at\": \"2026-03-15T10:00:00+00:00\",
                \"next_action\": \"ready_for_pr\"
              }
            }"""
        )
        return runtime, run_root

    @patch("symphony_runtime.daemon.create_pull_request")
    @patch("symphony_runtime.daemon.ensure_ready_for_pr")
    def test_create_pr_from_run_uses_ready_record_and_returns_url(self, ensure_ready, create_pr):
        create_pr.return_value = "https://github.com/o/r/pull/42"
        runtime, run_root = self._make_runtime_and_run_root()

        url = runtime.create_pr_from_run("lin-42")

        ensure_ready.assert_called_once_with(
            Path("/tmp/worktree"),
            expected_commit="abc123",
            expected_branch="feature/lin-42",
        )
        create_pr.assert_called_once_with(
            worktree_path=Path("/tmp/worktree"),
            base_branch="main",
            head_branch="feature/lin-42",
            title="LIN-42",
            body_path=run_root.resolve(strict=False) / "pr_handoff.md",
        )
        self.assertEqual(url, "https://github.com/o/r/pull/42")

    @patch("symphony_runtime.daemon.create_pull_request")
    @patch("symphony_runtime.daemon.ensure_ready_for_pr")
    def test_create_pr_from_run_writes_pr_opened_artifact(self, ensure_ready, create_pr):
        create_pr.return_value = "https://github.com/o/r/pull/42"
        runtime, run_root = self._make_runtime_and_run_root()

        url = runtime.create_pr_from_run("lin-42")

        self.assertEqual(url, "https://github.com/o/r/pull/42")
        payload = json.loads((run_root / "status.json").read_text())
        self.assertEqual(payload["human_gate"]["next_action"], "pr_opened")
        self.assertEqual(payload["pr"]["url"], "https://github.com/o/r/pull/42")
        self.assertIn("opened_at", payload["pr"])
        markdown = (run_root / "pr_opened.md").read_text()
        self.assertIn("https://github.com/o/r/pull/42", markdown)
        self.assertIn("Opened At:", markdown)

    @patch("symphony_runtime.daemon.create_pull_request")
    @patch("symphony_runtime.daemon.ensure_ready_for_pr")
    def test_create_pr_from_run_propagates_ensure_ready_failure(self, ensure_ready, create_pr):
        runtime, _ = self._make_runtime_and_run_root()
        ensure_ready.side_effect = RuntimeError("dirty worktree")

        with self.assertRaisesRegex(RuntimeError, "dirty worktree"):
            runtime.create_pr_from_run("lin-42")

        create_pr.assert_not_called()

    @patch("symphony_runtime.daemon.write_pr_review_snapshot")
    @patch("symphony_runtime.daemon.fetch_pr_review_comments")
    def test_refresh_pr_reviews_from_run_loads_opened_pr_and_writes_snapshot(
        self,
        fetch_pr_review_comments,
        write_pr_review_snapshot,
    ):
        runtime, run_root = self._make_runtime_and_run_root()
        write_pr_opened(run_root, "https://github.com/o/r/pull/42")
        fetch_pr_review_comments.return_value = '{"comments":[],"reviews":[]}'

        runtime.refresh_pr_reviews_from_run("lin-42")

        fetch_pr_review_comments.assert_called_once_with(
            "https://github.com/o/r/pull/42",
            Path("/tmp/worktree"),
        )
        write_pr_review_snapshot.assert_called_once_with(
            run_root.resolve(strict=False),
            '{"comments":[],"reviews":[]}',
        )

    def test_write_pr_review_snapshot_persists_review_json_and_markdown(self):
        runtime, run_root = self._make_runtime_and_run_root()
        del runtime

        write_pr_opened(run_root, "https://github.com/o/r/pull/42")
        review_json = json.dumps(
            {
                "comments": [
                    {
                        "id": "comment-1",
                        "body": "Please rename this",
                        "author": {"login": "reviewer1"},
                    }
                ],
                "reviews": [
                    {
                        "id": "review-1",
                        "state": "CHANGES_REQUESTED",
                        "body": "Need a test for this edge case",
                        "author": {"login": "reviewer2"},
                    }
                ],
            }
        )

        write_pr_review_snapshot(run_root, review_json)

        self.assertTrue((run_root / "pr_review_comments.json").exists())
        self.assertTrue((run_root / "pr_review_summary.md").exists())
        self.assertTrue((run_root / "pr_review_findings.json").exists())
        self.assertTrue((run_root / "pr_review_triage.md").exists())
        self.assertEqual((run_root / "pr_review_comments.json").read_text(), review_json)

        summary = (run_root / "pr_review_summary.md").read_text()
        self.assertIn("# PR Review Summary", summary)
        self.assertIn("Issue: LIN-42", summary)
        self.assertIn("PR URL: https://github.com/o/r/pull/42", summary)
        self.assertIn("Review snapshot captured.", summary)

        findings_payload = json.loads((run_root / "pr_review_findings.json").read_text())
        self.assertEqual(findings_payload["total_findings"], 2)
        self.assertEqual(findings_payload["blocking_count"], 1)
        self.assertEqual(
            findings_payload["unresolved_findings"],
            [
                {
                    "source": "comment",
                    "finding_id": "comment-1",
                    "author": "reviewer1",
                    "body": "Please rename this",
                    "is_blocking": False,
                },
                {
                    "source": "review",
                    "finding_id": "review-1",
                    "author": "reviewer2",
                    "body": "Need a test for this edge case",
                    "is_blocking": True,
                },
            ],
        )

        triage = (run_root / "pr_review_triage.md").read_text()
        self.assertIn("# PR Review Triage", triage)
        self.assertIn("Blocking Reviews: 1", triage)
        self.assertIn("Still Unresolved Findings: 2", triage)
        self.assertIn("Newly Introduced Findings: 0", triage)
        self.assertIn("Resolved Findings: 0", triage)
        self.assertIn("## Still Unresolved Findings", triage)
        self.assertIn("- [comment] reviewer1: Please rename this", triage)
        self.assertIn("- [review/blocking] reviewer2: Need a test for this edge case", triage)

        status_payload = json.loads((run_root / "status.json").read_text())
        self.assertIn("review_fetched_at", status_payload["pr"])
        self.assertEqual(status_payload["pr"]["review_comments_path"], "pr_review_comments.json")
        self.assertEqual(status_payload["pr"]["review_findings_path"], "pr_review_findings.json")
        self.assertEqual(status_payload["pr"]["review_triage_path"], "pr_review_triage.md")
        self.assertEqual(status_payload["pr"]["blocking_review_count"], 1)

        state_payload = json.loads((run_root / "state.json").read_text())
        self.assertIn("review_fetched_at", state_payload["pr"])
        self.assertEqual(state_payload["pr"]["review_comments_path"], "pr_review_comments.json")
        self.assertEqual(state_payload["pr"]["review_findings_path"], "pr_review_findings.json")
        self.assertEqual(state_payload["pr"]["review_triage_path"], "pr_review_triage.md")
        self.assertEqual(state_payload["pr"]["blocking_review_count"], 1)

    def test_write_pr_review_snapshot_first_snapshot_diff_uses_null_previous_findings_path(self):
        runtime, run_root = self._make_runtime_and_run_root()
        del runtime

        write_pr_opened(run_root, "https://github.com/o/r/pull/42")
        write_pr_review_snapshot(
            run_root,
            json.dumps(
                {
                    "comments": [
                        {
                            "id": "comment-1",
                            "body": "Please rename this",
                            "author": {"login": "reviewer1"},
                        }
                    ],
                    "reviews": [
                        {
                            "id": "review-1",
                            "state": "CHANGES_REQUESTED",
                            "body": "Need a test for this edge case",
                            "author": {"login": "reviewer2"},
                        }
                    ],
                }
            ),
        )

        diff_payload = json.loads((run_root / "pr_review_diff.json").read_text())
        self.assertIsNone(diff_payload["previous_findings_path"])
        self.assertEqual(diff_payload["current_findings_path"], "pr_review_findings.json")
        self.assertEqual(diff_payload["newly_introduced_count"], 0)
        self.assertEqual(diff_payload["resolved_count"], 0)
        self.assertEqual(diff_payload["newly_introduced_findings"], [])
        self.assertEqual(diff_payload["resolved_findings"], [])

    def test_write_pr_review_snapshot_preserves_previous_findings_and_records_diff_metadata(self):
        runtime, run_root = self._make_runtime_and_run_root()
        del runtime

        write_pr_opened(run_root, "https://github.com/o/r/pull/42")
        write_pr_review_snapshot(
            run_root,
            json.dumps(
                {
                    "comments": [
                        {
                            "id": "comment-1",
                            "body": "Please rename this",
                            "author": {"login": "reviewer1"},
                        }
                    ],
                    "reviews": [
                        {
                            "id": "review-1",
                            "state": "CHANGES_REQUESTED",
                            "body": "Need a test for this edge case",
                            "author": {"login": "reviewer2"},
                        }
                    ],
                }
            ),
        )

        write_pr_review_snapshot(
            run_root,
            json.dumps(
                {
                    "comments": [
                        {
                            "id": "comment-1",
                            "body": "Please rename this",
                            "author": {"login": "reviewer1"},
                        },
                        {
                            "id": "comment-2",
                            "body": "Document the fallback path",
                            "author": {"login": "reviewer3"},
                        },
                    ],
                    "reviews": [],
                }
            ),
        )

        previous_findings = json.loads((run_root / "pr_review_findings.previous.json").read_text())
        self.assertEqual(previous_findings["total_findings"], 2)
        self.assertEqual(previous_findings["blocking_count"], 1)
        self.assertEqual(
            previous_findings["unresolved_findings"],
            [
                {
                    "source": "comment",
                    "finding_id": "comment-1",
                    "author": "reviewer1",
                    "body": "Please rename this",
                    "is_blocking": False,
                },
                {
                    "source": "review",
                    "finding_id": "review-1",
                    "author": "reviewer2",
                    "body": "Need a test for this edge case",
                    "is_blocking": True,
                },
            ],
        )

        current_findings = json.loads((run_root / "pr_review_findings.json").read_text())
        self.assertEqual(current_findings["total_findings"], 2)
        self.assertEqual(current_findings["blocking_count"], 0)

        diff_payload = json.loads((run_root / "pr_review_diff.json").read_text())
        self.assertEqual(diff_payload["previous_findings_path"], "pr_review_findings.previous.json")
        self.assertEqual(diff_payload["current_findings_path"], "pr_review_findings.json")
        self.assertEqual(diff_payload["newly_introduced_count"], 1)
        self.assertEqual(diff_payload["resolved_count"], 1)
        self.assertEqual(
            diff_payload["newly_introduced_findings"],
            [
                {
                    "source": "comment",
                    "finding_id": "comment-2",
                    "author": "reviewer3",
                    "body": "Document the fallback path",
                    "is_blocking": False,
                }
            ],
        )
        self.assertEqual(
            diff_payload["resolved_findings"],
            [
                {
                    "source": "review",
                    "finding_id": "review-1",
                    "author": "reviewer2",
                    "body": "Need a test for this edge case",
                    "is_blocking": True,
                }
            ],
        )

        status_payload = json.loads((run_root / "status.json").read_text())
        self.assertEqual(status_payload["pr"]["previous_review_findings_path"], "pr_review_findings.previous.json")
        self.assertEqual(status_payload["pr"]["review_findings_path"], "pr_review_findings.json")
        self.assertEqual(status_payload["pr"]["review_diff_path"], "pr_review_diff.json")
        self.assertEqual(status_payload["pr"]["newly_introduced_findings_count"], 1)
        self.assertEqual(status_payload["pr"]["resolved_findings_count"], 1)

        state_payload = json.loads((run_root / "state.json").read_text())
        self.assertEqual(state_payload["pr"], status_payload["pr"])

        triage = (run_root / "pr_review_triage.md").read_text()
        self.assertEqual(
            triage,
            "# PR Review Triage\n"
            "\n"
            "Issue: LIN-42\n"
            "PR URL: https://github.com/o/r/pull/42\n"
            "Review Fetched At: " + status_payload["pr"]["review_fetched_at"] + "\n"
            "Blocking Reviews: 0\n"
            "Still Unresolved Findings: 2\n"
            "Newly Introduced Findings: 1\n"
            "Resolved Findings: 1\n"
            "\n"
            "## Still Unresolved Findings\n"
            "\n"
            "- [comment] reviewer1: Please rename this\n"
            "- [comment] reviewer3: Document the fallback path\n"
            "\n"
            "## Newly Introduced Findings\n"
            "\n"
            "- [comment] reviewer3: Document the fallback path\n"
            "\n"
            "## Resolved Findings\n"
            "\n"
            "- [review/blocking] reviewer2: Need a test for this edge case\n",
        )

    def test_write_pr_review_acknowledgement_includes_compact_diff_summary(self):
        runtime, run_root = self._make_runtime_and_run_root()
        del runtime
        write_pr_opened(run_root, "https://github.com/o/r/pull/42")
        write_pr_review_snapshot(
            run_root,
            json.dumps(
                {
                    "comments": [
                        {
                            "id": "comment-1",
                            "body": "Please rename this",
                            "author": {"login": "reviewer1"},
                        }
                    ],
                    "reviews": [
                        {
                            "id": "review-1",
                            "state": "CHANGES_REQUESTED",
                            "body": "Need a test for this edge case",
                            "author": {"login": "reviewer2"},
                        }
                    ],
                }
            ),
        )
        write_pr_review_snapshot(
            run_root,
            json.dumps(
                {
                    "comments": [
                        {
                            "id": "comment-1",
                            "body": "Please rename this",
                            "author": {"login": "reviewer1"},
                        },
                        {
                            "id": "comment-2",
                            "body": "Document the fallback path",
                            "author": {"login": "reviewer3"},
                        },
                    ],
                    "reviews": [],
                }
            ),
        )

        write_pr_review_acknowledgement(run_root, "addressed", "Handled locally")

        diff_payload = json.loads((run_root / "pr_review_diff.json").read_text())
        acknowledgement = (run_root / "pr_review_acknowledgement.md").read_text()
        self.assertIn("Blocking Reviews: 0", acknowledgement)
        self.assertIn("Still Unresolved Findings: 2", acknowledgement)
        self.assertIn(
            f"Newly Introduced Findings: {diff_payload['newly_introduced_count']}",
            acknowledgement,
        )
        self.assertIn(f"Resolved Findings: {diff_payload['resolved_count']}", acknowledgement)
        self.assertIn("## Still Unresolved Findings", acknowledgement)
        self.assertIn("## Newly Introduced Findings", acknowledgement)
        self.assertIn("## Resolved Findings", acknowledgement)
        self.assertIn("- [comment] reviewer1: Please rename this", acknowledgement)
        self.assertIn("- [comment] reviewer3: Document the fallback path", acknowledgement)
        self.assertIn("- [review/blocking] reviewer2: Need a test for this edge case", acknowledgement)
        self.assertLessEqual(len(acknowledgement.splitlines()), 20)

    def test_get_pr_review_status_from_run_returns_triage_summary(self):
        runtime, run_root = self._make_runtime_and_run_root()
        write_pr_opened(run_root, "https://github.com/o/r/pull/42")
        write_pr_review_snapshot(
            run_root,
            json.dumps(
                {
                    "comments": [],
                    "reviews": [
                        {
                            "id": "review-1",
                            "state": "CHANGES_REQUESTED",
                            "body": "Need a test for this edge case",
                            "author": {"login": "reviewer2"},
                        }
                    ],
                }
            ),
        )

        status = runtime.get_pr_review_status_from_run(run_root.name)

        self.assertEqual(status["issue_key"], "LIN-42")
        self.assertEqual(status["pr_url"], "https://github.com/o/r/pull/42")
        self.assertEqual(status["blocking_review_count"], 1)
        self.assertEqual(status["unresolved_findings_count"], 1)
        self.assertEqual(status["newly_introduced_findings_count"], 0)
        self.assertEqual(status["resolved_findings_count"], 0)
        self.assertIn("pr_review_diff.json", status["review_diff_path"])
        self.assertIn("pr_review_triage.md", status["review_triage_path"])

    def test_get_pr_review_status_from_run_rejects_non_pr_opened_run_state(self):
        runtime, run_root = self._make_runtime_and_run_root()

        with self.assertRaisesRegex(ValueError, "Expected pr_opened next action"):
            runtime.get_pr_review_status_from_run(run_root.name)

    def test_get_pr_review_status_from_run_derives_unresolved_findings_count_from_artifact(self):
        runtime, run_root = self._make_runtime_and_run_root()
        write_pr_opened(run_root, "https://github.com/o/r/pull/42")
        write_pr_review_snapshot(
            run_root,
            json.dumps(
                {
                    "comments": [
                        {
                            "id": "comment-1",
                            "body": "Please rename this",
                            "author": {"login": "reviewer1"},
                        }
                    ],
                    "reviews": [
                        {
                            "id": "review-1",
                            "state": "CHANGES_REQUESTED",
                            "body": "Need a test for this edge case",
                            "author": {"login": "reviewer2"},
                        }
                    ],
                }
            ),
        )

        status = runtime.get_pr_review_status_from_run(run_root.name)

        self.assertEqual(status["blocking_review_count"], 1)
        self.assertEqual(status["unresolved_findings_count"], 2)

    def test_get_pr_review_status_from_run_rejects_missing_review_snapshot_metadata(self):
        runtime, run_root = self._make_runtime_and_run_root()
        write_pr_opened(run_root, "https://github.com/o/r/pull/42")
        write_pr_review_snapshot(run_root, json.dumps({"comments": [], "reviews": []}))
        status_payload = json.loads((run_root / "status.json").read_text())
        status_payload["pr"].pop("review_triage_path", None)
        (run_root / "status.json").write_text(json.dumps(status_payload, indent=2))

        with self.assertRaisesRegex(ValueError, "review_triage_path"):
            runtime.get_pr_review_status_from_run(run_root.name)

    def test_get_pr_review_status_from_run_rejects_invalid_blocking_review_count(self):
        runtime, run_root = self._make_runtime_and_run_root()
        write_pr_opened(run_root, "https://github.com/o/r/pull/42")
        write_pr_review_snapshot(run_root, json.dumps({"comments": [], "reviews": []}))
        status_payload = json.loads((run_root / "status.json").read_text())
        status_payload["pr"]["blocking_review_count"] = -1
        (run_root / "status.json").write_text(json.dumps(status_payload, indent=2))

        with self.assertRaisesRegex(ValueError, "blocking_review_count"):
            runtime.get_pr_review_status_from_run(run_root.name)

    def test_get_pr_review_status_from_run_rejects_missing_referenced_triage_artifact(self):
        runtime, run_root = self._make_runtime_and_run_root()
        write_pr_opened(run_root, "https://github.com/o/r/pull/42")
        write_pr_review_snapshot(run_root, json.dumps({"comments": [], "reviews": []}))
        (run_root / "pr_review_triage.md").unlink()

        with self.assertRaisesRegex(ValueError, "pr_review_triage.md"):
            runtime.get_pr_review_status_from_run(run_root.name)

    def test_get_pr_review_status_from_run_rejects_status_state_review_metadata_mismatch(self):
        runtime, run_root = self._make_runtime_and_run_root()
        write_pr_opened(run_root, "https://github.com/o/r/pull/42")
        write_pr_review_snapshot(run_root, json.dumps({"comments": [], "reviews": []}))
        state_payload = json.loads((run_root / "state.json").read_text())
        state_payload["pr"]["review_findings_path"] = "other_findings.json"
        (run_root / "state.json").write_text(json.dumps(state_payload, indent=2))

        with self.assertRaisesRegex(ValueError, "state.json"):
            runtime.get_pr_review_status_from_run(run_root.name)

    def test_get_pr_review_status_from_run_rejects_absolute_run_ref_outside_runs_root(self):
        runtime, run_root = self._make_runtime_and_run_root()
        write_pr_opened(run_root, "https://github.com/o/r/pull/42")
        write_pr_review_snapshot(run_root, json.dumps({"comments": [], "reviews": []}))

        outside_run_root = runtime.config.workspace_root / "external-run"
        outside_run_root.mkdir(parents=True)
        for artifact_name in (
            "status.json",
            "state.json",
            "pr_review_comments.json",
            "pr_review_findings.json",
            "pr_review_triage.md",
        ):
            (outside_run_root / artifact_name).write_text((run_root / artifact_name).read_text())

        with self.assertRaisesRegex(ValueError, "runs_root"):
            runtime.get_pr_review_status_from_run(str(outside_run_root))

    def test_get_pr_review_status_from_run_rejects_relative_run_ref_escaping_runs_root(self):
        runtime, run_root = self._make_runtime_and_run_root()
        write_pr_opened(run_root, "https://github.com/o/r/pull/42")
        write_pr_review_snapshot(run_root, json.dumps({"comments": [], "reviews": []}))

        outside_run_root = runtime.config.workspace_root / "external-run"
        outside_run_root.mkdir(parents=True)
        for artifact_name in (
            "status.json",
            "state.json",
            "pr_review_comments.json",
            "pr_review_findings.json",
            "pr_review_triage.md",
        ):
            (outside_run_root / artifact_name).write_text((run_root / artifact_name).read_text())

        escape_ref = str(Path("..").joinpath(outside_run_root.name))
        with self.assertRaisesRegex(ValueError, "runs_root"):
            runtime.get_pr_review_status_from_run(escape_ref)

    def test_acknowledge_pr_reviews_from_run_writes_explicit_state_and_state_metadata(self):
        runtime, run_root = self._make_runtime_and_run_root()
        write_pr_opened(run_root, "https://github.com/o/r/pull/42")
        write_pr_review_snapshot(
            run_root,
            json.dumps(
                {
                    "comments": [
                        {
                            "id": "comment-1",
                            "body": "Please rename this",
                            "author": {"login": "reviewer1"},
                        }
                    ],
                    "reviews": [
                        {
                            "id": "review-1",
                            "state": "CHANGES_REQUESTED",
                            "body": "Need a test for this edge case",
                            "author": {"login": "reviewer2"},
                        }
                    ],
                }
            ),
        )

        runtime.acknowledge_pr_reviews_from_run("lin-42", "addressed", "Handled locally")

        acknowledgement_path = run_root / "pr_review_acknowledgement.md"
        self.assertTrue(acknowledgement_path.exists())
        acknowledgement = acknowledgement_path.read_text()
        self.assertIn("# PR Review Acknowledgement", acknowledgement)
        self.assertIn("Issue: LIN-42", acknowledgement)
        self.assertIn("PR URL: https://github.com/o/r/pull/42", acknowledgement)
        self.assertIn("State: addressed", acknowledgement)
        self.assertIn("Note: Handled locally", acknowledgement)
        self.assertIn("Blocking Reviews: 1", acknowledgement)
        self.assertIn("Unresolved Findings: 2", acknowledgement)
        self.assertIn("- [comment] reviewer1: Please rename this", acknowledgement)
        self.assertIn("- [review/blocking] reviewer2: Need a test for this edge case", acknowledgement)

        status_payload = json.loads((run_root / "status.json").read_text())
        acknowledgement_payload = status_payload["pr"]["review_acknowledgement"]
        self.assertEqual(acknowledgement_payload["path"], "pr_review_acknowledgement.md")
        self.assertEqual(acknowledgement_payload["state"], "addressed")
        self.assertEqual(acknowledgement_payload["note"], "Handled locally")
        self.assertEqual(acknowledgement_payload["has_note"], True)
        self.assertIn("acknowledged_at", acknowledgement_payload)

        state_payload = json.loads((run_root / "state.json").read_text())
        self.assertEqual(state_payload["pr"]["review_acknowledgement"], acknowledgement_payload)

    def test_write_pr_review_acknowledgement_accepts_all_explicit_states(self):
        runtime, run_root = self._make_runtime_and_run_root()
        del runtime
        write_pr_opened(run_root, "https://github.com/o/r/pull/42")
        write_pr_review_snapshot(run_root, json.dumps({"comments": [], "reviews": []}))

        for state in VALID_ACKNOWLEDGEMENT_STATES:
            write_pr_review_acknowledgement(run_root, state, "")
            acknowledgement_payload = json.loads((run_root / "status.json").read_text())["pr"]["review_acknowledgement"]
            self.assertEqual(acknowledgement_payload["state"], state)
            self.assertEqual(acknowledgement_payload["note"], "")
            self.assertEqual(acknowledgement_payload["has_note"], False)

    def test_write_pr_review_acknowledgement_rejects_unknown_state(self):
        runtime, run_root = self._make_runtime_and_run_root()
        del runtime
        write_pr_opened(run_root, "https://github.com/o/r/pull/42")
        write_pr_review_snapshot(run_root, json.dumps({"comments": [], "reviews": []}))

        with self.assertRaisesRegex(ValueError, "state"):
            write_pr_review_acknowledgement(run_root, "handled", "Handled locally")

    def test_write_pr_review_acknowledgement_rejects_malformed_unresolved_findings_entries(self):
        runtime, run_root = self._make_runtime_and_run_root()
        del runtime
        write_pr_opened(run_root, "https://github.com/o/r/pull/42")
        write_pr_review_snapshot(run_root, json.dumps({"comments": [], "reviews": []}))

        findings_payload = json.loads((run_root / "pr_review_findings.json").read_text())
        findings_payload["unresolved_findings"] = ["bad-entry"]
        (run_root / "pr_review_findings.json").write_text(json.dumps(findings_payload, indent=2))

        with self.assertRaisesRegex(ValueError, "unresolved_findings"):
            write_pr_review_acknowledgement(run_root, "reviewed", "Handled locally")

    def test_prepare_merge_from_run_writes_guarded_local_merge_artifacts(self):
        runtime, run_root = self._make_runtime_and_run_root()
        write_human_gate_preview_state(
            run_root=run_root,
            issue_key="LIN-42",
            branch="feature/lin-42",
            commit_sha="abc123",
            recommendation="review",
        )
        write_summary_artifacts(
            run_root=run_root,
            summary="Summary",
            verification="Verification",
            review="Review",
            status_payload=json.loads((run_root / "status.json").read_text()),
        )
        write_pr_opened(run_root, "https://github.com/o/r/pull/42")
        write_pr_review_snapshot(run_root, json.dumps({"comments": [], "reviews": []}))
        write_pr_review_acknowledgement(run_root, "addressed", "Handled locally")

        merge_preparation = runtime.prepare_merge_from_run("lin-42")
        resolved_run_root = run_root.resolve(strict=False)

        self.assertEqual(merge_preparation["run_ref"], "lin-42")
        self.assertEqual(merge_preparation["issue_key"], "LIN-42")
        self.assertEqual(merge_preparation["branch"], "feature/lin-42")
        self.assertEqual(merge_preparation["commit_sha"], "abc123")
        self.assertEqual(merge_preparation["pr_url"], "https://github.com/o/r/pull/42")
        self.assertEqual(merge_preparation["blocking_review_count"], 0)
        self.assertEqual(merge_preparation["acknowledgement_state"], "addressed")
        self.assertEqual(merge_preparation["summary_path"], str(resolved_run_root / "summary.md"))
        self.assertEqual(merge_preparation["verification_path"], str(resolved_run_root / "verification.md"))
        self.assertEqual(merge_preparation["review_path"], str(resolved_run_root / "review.md"))
        self.assertEqual(merge_preparation["human_gate_package_path"], str(resolved_run_root / "human_gate_package.md"))
        self.assertEqual(merge_preparation["human_gate_package_json_path"], str(resolved_run_root / "human_gate_package.json"))
        self.assertEqual(merge_preparation["merge_preparation_path"], str(resolved_run_root / "merge_preparation.md"))

        merge_json_path = run_root / "merge_preparation.json"
        merge_md_path = run_root / "merge_preparation.md"
        self.assertTrue(merge_json_path.exists())
        self.assertTrue(merge_md_path.exists())

        merge_json = json.loads(merge_json_path.read_text())
        self.assertEqual(merge_json["run_ref"], "lin-42")
        self.assertEqual(merge_json["pr_url"], "https://github.com/o/r/pull/42")
        self.assertEqual(merge_json["blocking_review_count"], 0)
        self.assertEqual(merge_json["acknowledgement_state"], "addressed")
        self.assertEqual(merge_json["summary_path"], "summary.md")
        self.assertEqual(merge_json["verification_path"], "verification.md")
        self.assertEqual(merge_json["review_path"], "review.md")
        self.assertEqual(merge_json["human_gate_package_path"], "human_gate_package.md")
        self.assertEqual(merge_json["human_gate_package_json_path"], "human_gate_package.json")

        merge_md = merge_md_path.read_text()
        self.assertIn("# Merge Preparation", merge_md)
        self.assertIn("PR URL: https://github.com/o/r/pull/42", merge_md)
        self.assertIn("Acknowledgement State: addressed", merge_md)
        self.assertIn("Human Gate Package JSON: human_gate_package.json", merge_md)

        status_payload = json.loads((run_root / "status.json").read_text())
        state_payload = json.loads((run_root / "state.json").read_text())
        self.assertEqual(status_payload["pr"]["merge_preparation"]["json_path"], "merge_preparation.json")
        self.assertEqual(status_payload["pr"]["merge_preparation"]["markdown_path"], "merge_preparation.md")
        self.assertEqual(status_payload["pr"]["merge_preparation"]["human_gate_package_path"], "human_gate_package.md")
        self.assertEqual(status_payload["pr"]["merge_preparation"]["human_gate_package_json_path"], "human_gate_package.json")
        self.assertEqual(status_payload["pr"]["merge_preparation"]["acknowledgement_state"], "addressed")
        self.assertEqual(state_payload["pr"]["merge_preparation"], status_payload["pr"]["merge_preparation"])
        self.assertEqual(status_payload["status"], "done")
        self.assertEqual(state_payload["status"], "done")

    def test_prepare_merge_from_run_rejects_non_addressed_acknowledgement(self):
        runtime, run_root = self._make_runtime_and_run_root()
        write_human_gate_preview_state(
            run_root=run_root,
            issue_key="LIN-42",
            branch="feature/lin-42",
            commit_sha="abc123",
            recommendation="review",
        )
        write_summary_artifacts(
            run_root=run_root,
            summary="Summary",
            verification="Verification",
            review="Review",
            status_payload=json.loads((run_root / "status.json").read_text()),
        )
        write_pr_opened(run_root, "https://github.com/o/r/pull/42")
        write_pr_review_snapshot(run_root, json.dumps({"comments": [], "reviews": []}))
        write_pr_review_acknowledgement(run_root, "reviewed", "Looked at it")

        with self.assertRaisesRegex(ValueError, "addressed"):
            runtime.prepare_merge_from_run("lin-42")

    def test_prepare_merge_from_run_rejects_blocking_reviews(self):
        runtime, run_root = self._make_runtime_and_run_root()
        write_human_gate_preview_state(
            run_root=run_root,
            issue_key="LIN-42",
            branch="feature/lin-42",
            commit_sha="abc123",
            recommendation="review",
        )
        write_summary_artifacts(
            run_root=run_root,
            summary="Summary",
            verification="Verification",
            review="Review",
            status_payload=json.loads((run_root / "status.json").read_text()),
        )
        write_pr_opened(run_root, "https://github.com/o/r/pull/42")
        write_pr_review_snapshot(
            run_root,
            json.dumps({
                "comments": [],
                "reviews": [
                    {
                        "id": "review-1",
                        "state": "CHANGES_REQUESTED",
                        "body": "Please fix",
                        "author": {"login": "reviewer1"},
                    }
                ],
            }),
        )
        write_pr_review_acknowledgement(run_root, "addressed", "Handled locally")

        with self.assertRaisesRegex(ValueError, "blocking_review_count == 0"):
            runtime.prepare_merge_from_run("lin-42")

    def test_prepare_merge_from_run_rejects_missing_required_execution_artifact(self):
        runtime, run_root = self._make_runtime_and_run_root()
        write_human_gate_preview_state(
            run_root=run_root,
            issue_key="LIN-42",
            branch="feature/lin-42",
            commit_sha="abc123",
            recommendation="review",
        )
        write_summary_artifacts(
            run_root=run_root,
            summary="Summary",
            verification="Verification",
            review="Review",
            status_payload=json.loads((run_root / "status.json").read_text()),
        )
        write_pr_opened(run_root, "https://github.com/o/r/pull/42")
        write_pr_review_snapshot(run_root, json.dumps({"comments": [], "reviews": []}))
        write_pr_review_acknowledgement(run_root, "addressed", "Handled locally")
        (run_root / "verification.md").unlink()

        with self.assertRaisesRegex(ValueError, r"existing verification\.md"):
            runtime.prepare_merge_from_run("lin-42")

    def test_prepare_merge_from_run_rejects_missing_human_gate_package_json_artifact(self):
        runtime, run_root = self._make_runtime_and_run_root()
        write_human_gate_preview_state(
            run_root=run_root,
            issue_key="LIN-42",
            branch="feature/lin-42",
            commit_sha="abc123",
            recommendation="review",
        )
        write_summary_artifacts(
            run_root=run_root,
            summary="Summary",
            verification="Verification",
            review="Review",
            status_payload=json.loads((run_root / "status.json").read_text()),
        )
        write_pr_opened(run_root, "https://github.com/o/r/pull/42")
        write_pr_review_snapshot(run_root, json.dumps({"comments": [], "reviews": []}))
        write_pr_review_acknowledgement(run_root, "addressed", "Handled locally")
        (run_root / "human_gate_package.json").unlink()

        with self.assertRaisesRegex(ValueError, r"existing human_gate_package\.json"):
            runtime.prepare_merge_from_run("lin-42")

    def test_prepare_merge_from_run_rejects_non_opened_pr_state(self):
        runtime, run_root = self._make_runtime_and_run_root()
        write_human_gate_preview_state(
            run_root=run_root,
            issue_key="LIN-42",
            branch="feature/lin-42",
            commit_sha="abc123",
            recommendation="review",
        )
        write_summary_artifacts(
            run_root=run_root,
            summary="Summary",
            verification="Verification",
            review="Review",
            status_payload=json.loads((run_root / "status.json").read_text()),
        )

        with self.assertRaisesRegex(ValueError, "Expected pr_opened next action"):
            runtime.prepare_merge_from_run("lin-42")

    def test_prepare_merge_from_run_is_local_bookkeeping_only(self):
        runtime, run_root = self._make_runtime_and_run_root()
        write_human_gate_preview_state(
            run_root=run_root,
            issue_key="LIN-42",
            branch="feature/lin-42",
            commit_sha="abc123",
            recommendation="review",
        )
        write_summary_artifacts(
            run_root=run_root,
            summary="Summary",
            verification="Verification",
            review="Review",
            status_payload=json.loads((run_root / "status.json").read_text()),
        )
        write_pr_opened(run_root, "https://github.com/o/r/pull/42")
        write_pr_review_snapshot(run_root, json.dumps({"comments": [], "reviews": []}))
        write_pr_review_acknowledgement(run_root, "addressed", "Handled locally")

        runtime.linear_client = Mock()

        merge_preparation = runtime.prepare_merge_from_run("lin-42")

        runtime.linear_client.add_comment.assert_not_called()
        runtime.linear_client.update_issue_status.assert_not_called()
        status_payload = json.loads((run_root / "status.json").read_text())
        self.assertEqual(status_payload["status"], "done")
        self.assertEqual(status_payload["human_gate"]["next_action"], "pr_opened")
        self.assertEqual(merge_preparation["merge_preparation_path"], str(run_root.resolve(strict=False) / "merge_preparation.md"))


if __name__ == "__main__":
    unittest.main()
