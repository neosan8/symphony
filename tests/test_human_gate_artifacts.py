import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from symphony_runtime.run_store import (
    write_human_gate_decision,
    write_human_gate_handoff,
    write_pr_opened,
    write_pr_review_acknowledgement,
    write_pr_review_snapshot,
    write_summary_artifacts,
)


class HumanGateArtifactTests(unittest.TestCase):
    def test_write_summary_artifacts_persists_summary_verification_and_review_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir)

            write_summary_artifacts(
                run_root=run_root,
                summary="# Summary\nDone.",
                verification="# Verification\nPending.",
                review="# Review\nPending.",
                status_payload={"status": "human_gate"},
            )

            status_payload = json.loads((run_root / "status.json").read_text())
            self.assertEqual(status_payload["summary_path"], "summary.md")
            self.assertEqual(status_payload["verification_path"], "verification.md")
            self.assertEqual(status_payload["review_path"], "review.md")

    def test_write_human_gate_handoff_persists_operator_context(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir)

            write_human_gate_handoff(
                run_root=run_root,
                issue_id="issue-id-123",
                issue_key="LIN-42",
                branch="feature/lin-42",
                worktree_path="/tmp/worktrees/lin-42",
                base_branch="main",
                commit_sha="abc123",
                recommendation="review",
            )

            payload = json.loads((run_root / "status.json").read_text())
            self.assertEqual(payload["issue_id"], "issue-id-123")
            self.assertEqual(payload["issue_key"], "LIN-42")
            self.assertEqual(payload["branch"], "feature/lin-42")
            self.assertEqual(payload["worktree_path"], "/tmp/worktrees/lin-42")
            self.assertEqual(payload["base_branch"], "main")
            self.assertEqual(payload["commit_sha"], "abc123")
            self.assertEqual(
                payload["human_gate"],
                {
                    "recommendation": "review",
                    "decision_required": True,
                    "decision_applied": False,
                },
            )
            self.assertNotIn("summary_path", payload)
            self.assertNotIn("verification_path", payload)
            self.assertNotIn("review_path", payload)

            state_payload = json.loads((run_root / "state.json").read_text())
            self.assertEqual(state_payload["issue_id"], "issue-id-123")
            self.assertEqual(state_payload["issue_key"], "LIN-42")
            self.assertEqual(state_payload["branch"], "feature/lin-42")
            self.assertEqual(state_payload["worktree_path"], "/tmp/worktrees/lin-42")
            self.assertEqual(state_payload["base_branch"], "main")
            self.assertEqual(state_payload["commit_sha"], "abc123")
            self.assertEqual(
                state_payload["human_gate"],
                {
                    "recommendation": "review",
                    "decision_required": True,
                    "decision_applied": False,
                },
            )
            self.assertNotIn("summary_path", state_payload)
            self.assertNotIn("verification_path", state_payload)
            self.assertNotIn("review_path", state_payload)

    def test_write_human_gate_handoff_preserves_persisted_artifact_paths_in_status_and_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir)

            write_summary_artifacts(
                run_root=run_root,
                summary="# Summary\nDone.",
                verification="# Verification\nPending.",
                review="# Review\nPending.",
                status_payload={"status": "human_gate"},
            )

            write_human_gate_handoff(
                run_root=run_root,
                issue_id="issue-id-123",
                issue_key="LIN-42",
                branch="feature/lin-42",
                worktree_path="/tmp/worktrees/lin-42",
                base_branch="main",
                commit_sha="abc123",
                recommendation="review",
            )

            status_payload = json.loads((run_root / "status.json").read_text())
            self.assertEqual(status_payload["summary_path"], "summary.md")
            self.assertEqual(status_payload["verification_path"], "verification.md")
            self.assertEqual(status_payload["review_path"], "review.md")

            state_payload = json.loads((run_root / "state.json").read_text())
            self.assertEqual(state_payload["summary_path"], "summary.md")
            self.assertEqual(state_payload["verification_path"], "verification.md")
            self.assertEqual(state_payload["review_path"], "review.md")

    def test_write_human_gate_handoff_restores_artifact_paths_from_state_when_status_is_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir)

            write_summary_artifacts(
                run_root=run_root,
                summary="# Summary\nDone.",
                verification="# Verification\nPending.",
                review="# Review\nPending.",
                status_payload={"status": "human_gate"},
            )

            (run_root / "status.json").unlink()

            write_human_gate_handoff(
                run_root=run_root,
                issue_id="issue-id-123",
                issue_key="LIN-42",
                branch="feature/lin-42",
                worktree_path="/tmp/worktrees/lin-42",
                base_branch="main",
                commit_sha="abc123",
                recommendation="review",
            )

            status_payload = json.loads((run_root / "status.json").read_text())
            self.assertEqual(status_payload["summary_path"], "summary.md")
            self.assertEqual(status_payload["verification_path"], "verification.md")
            self.assertEqual(status_payload["review_path"], "review.md")

            state_payload = json.loads((run_root / "state.json").read_text())
            self.assertEqual(state_payload["summary_path"], "summary.md")
            self.assertEqual(state_payload["verification_path"], "verification.md")
            self.assertEqual(state_payload["review_path"], "review.md")

    def test_write_human_gate_handoff_writes_package_immediately_when_artifacts_exist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir)

            write_summary_artifacts(
                run_root=run_root,
                summary="# Summary\nDone.",
                verification="# Verification\nPassed.",
                review="# Review\nLooks good.",
                status_payload={"status": "in_progress", "issue_key": "LIN-42"},
            )

            write_human_gate_handoff(
                run_root=run_root,
                issue_id="issue-id-123",
                issue_key="LIN-42",
                branch="feature/lin-42",
                worktree_path="/tmp/worktrees/lin-42",
                base_branch="main",
                commit_sha="abc123",
                recommendation="review",
            )

            self.assertTrue((run_root / "human_gate_package.json").exists())
            self.assertTrue((run_root / "human_gate_package.md").exists())

            status_payload = json.loads((run_root / "status.json").read_text())
            self.assertEqual(status_payload["human_gate"]["package_json_path"], "human_gate_package.json")
            self.assertEqual(status_payload["human_gate"]["package_markdown_path"], "human_gate_package.md")

            state_payload = json.loads((run_root / "state.json").read_text())
            self.assertEqual(state_payload["human_gate"]["package_json_path"], "human_gate_package.json")
            self.assertEqual(state_payload["human_gate"]["package_markdown_path"], "human_gate_package.md")

            markdown = (run_root / "human_gate_package.md").read_text()
            self.assertIn("Issue: LIN-42", markdown)
            self.assertIn("Status: human_gate", markdown)
            self.assertIn("Summary: summary.md", markdown)
            self.assertIn("Verification: verification.md", markdown)
            self.assertIn("Review: review.md", markdown)
            self.assertIn("Recommendation: review", markdown)

    def test_write_human_gate_package_writes_json_and_markdown_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir)

            write_summary_artifacts(
                run_root=run_root,
                summary="# Summary\nDone.",
                verification="# Verification\nPassed.",
                review="# Review\nLooks good.",
                status_payload={"status": "human_gate", "issue_key": "LIN-42"},
            )
            write_human_gate_handoff(
                run_root=run_root,
                issue_id="issue-id-123",
                issue_key="LIN-42",
                branch="feature/lin-42",
                worktree_path="/tmp/worktrees/lin-42",
                base_branch="main",
                commit_sha="abc123",
                recommendation="review",
            )
            write_human_gate_decision(
                run_root=run_root,
                status="done",
                decision="approve",
                issue_key="LIN-42",
                note="Ship it",
            )
            write_pr_opened(run_root, "https://github.com/o/r/pull/42")
            write_pr_review_snapshot(run_root, json.dumps({"comments": [], "reviews": []}))
            write_pr_review_acknowledgement(run_root, "addressed", "Handled locally")

            self.assertTrue((run_root / "human_gate_package.json").exists())
            self.assertTrue((run_root / "human_gate_package.md").exists())

            status_payload = json.loads((run_root / "status.json").read_text())
            self.assertEqual(status_payload["human_gate"]["package_json_path"], "human_gate_package.json")
            self.assertEqual(status_payload["human_gate"]["package_markdown_path"], "human_gate_package.md")

    def test_write_human_gate_decision_persists_auditable_metadata_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir)

            write_human_gate_handoff(
                run_root=run_root,
                issue_id="issue-id-123",
                issue_key="LIN-42",
                branch="feature/lin-42",
                worktree_path="/tmp/worktrees/lin-42",
                base_branch="main",
                commit_sha="abc123",
                recommendation="review",
            )

            write_human_gate_decision(
                run_root=run_root,
                status="done",
                decision="approve",
                issue_key="LIN-42",
                note="Ship it",
            )

            status_payload = json.loads((run_root / "status.json").read_text())
            self.assertEqual(status_payload["status"], "done")
            self.assertEqual(status_payload["issue_id"], "issue-id-123")
            self.assertEqual(status_payload["issue_key"], "LIN-42")
            self.assertEqual(status_payload["branch"], "feature/lin-42")
            self.assertEqual(status_payload["worktree_path"], "/tmp/worktrees/lin-42")
            self.assertEqual(status_payload["base_branch"], "main")
            self.assertEqual(status_payload["commit_sha"], "abc123")
            self.assertEqual(status_payload["human_gate"]["recommendation"], "review")
            self.assertEqual(status_payload["human_gate"]["decision"], "approve")
            self.assertEqual(status_payload["human_gate"]["note"], "Ship it")
            self.assertEqual(status_payload["human_gate"]["next_action"], "ready_for_pr")
            self.assertFalse(status_payload["human_gate"]["decision_required"])
            self.assertTrue(status_payload["human_gate"]["decision_applied"])
            self.assertIn("applied_at", status_payload["human_gate"])

            state_payload = json.loads((run_root / "state.json").read_text())
            self.assertEqual(state_payload["status"], "done")
            self.assertEqual(state_payload["issue_id"], "issue-id-123")
            self.assertEqual(state_payload["issue_key"], "LIN-42")
            self.assertEqual(state_payload["branch"], "feature/lin-42")
            self.assertEqual(state_payload["worktree_path"], "/tmp/worktrees/lin-42")
            self.assertEqual(state_payload["base_branch"], "main")
            self.assertEqual(state_payload["commit_sha"], "abc123")
            self.assertEqual(state_payload["human_gate"]["recommendation"], "review")
            self.assertEqual(state_payload["human_gate"]["decision"], "approve")
            self.assertEqual(state_payload["human_gate"]["note"], "Ship it")
            self.assertEqual(state_payload["human_gate"]["next_action"], "ready_for_pr")
            self.assertFalse(state_payload["human_gate"]["decision_required"])
            self.assertTrue(state_payload["human_gate"]["decision_applied"])
            self.assertIn("applied_at", state_payload["human_gate"])

            self.assertTrue((run_root / "human_gate_decision.md").exists())
            markdown = (run_root / "human_gate_decision.md").read_text()
            self.assertIn("Issue: LIN-42", markdown)
            self.assertIn("Decision: approve", markdown)
            self.assertIn("Note: Ship it", markdown)
            self.assertIn("Next Action: ready_for_pr", markdown)
            self.assertIn("Applied At:", markdown)

    def test_write_human_gate_decision_writes_pr_handoff_for_approved_runs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir)

            write_human_gate_handoff(
                run_root=run_root,
                issue_id="issue-id-123",
                issue_key="LIN-42",
                branch="feature/lin-42",
                worktree_path="/tmp/worktrees/lin-42",
                base_branch="main",
                commit_sha="abc123",
                recommendation="review",
            )

            write_human_gate_decision(
                run_root=run_root,
                status="done",
                decision="approve",
                issue_key="LIN-42",
                note="Ship it",
            )

            self.assertTrue((run_root / "pr_handoff.md").exists())
            handoff = (run_root / "pr_handoff.md").read_text()
            self.assertIn("Issue: LIN-42", handoff)
            self.assertIn("Branch: feature/lin-42", handoff)
            self.assertIn("Worktree: /tmp/worktrees/lin-42", handoff)
            self.assertIn("Base Branch: main", handoff)
            self.assertIn("Commit: abc123", handoff)
            self.assertIn("Note: Ship it", handoff)
            self.assertIn("Next Action: ready_for_pr", handoff)

    def test_write_human_gate_decision_approve_requires_full_pr_handoff_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir)
            (run_root / "status.json").write_text(json.dumps({
                "status": "human_gate",
                "issue_key": "LIN-42",
                "human_gate": {
                    "recommendation": "review",
                    "decision_required": True,
                    "decision_applied": False,
                },
            }))

            with self.assertRaisesRegex(ValueError, "Approved Human Gate decision requires non-empty handoff fields: branch, commit_sha, worktree_path, base_branch"):
                write_human_gate_decision(
                    run_root=run_root,
                    status="done",
                    decision="approve",
                    issue_key="LIN-42",
                    note="Ship it",
                )

            self.assertFalse((run_root / "pr_handoff.md").exists())

    def test_write_human_gate_decision_approve_requires_worktree_path_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir)

            write_human_gate_handoff(
                run_root=run_root,
                issue_id="issue-id-123",
                issue_key="LIN-42",
                branch="feature/lin-42",
                worktree_path="",
                base_branch="main",
                commit_sha="abc123",
                recommendation="review",
            )

            with self.assertRaisesRegex(ValueError, "Approved Human Gate decision requires non-empty handoff fields: worktree_path"):
                write_human_gate_decision(
                    run_root=run_root,
                    status="done",
                    decision="approve",
                    issue_key="LIN-42",
                    note="Ship it",
                )

            self.assertFalse((run_root / "pr_handoff.md").exists())

    def test_write_human_gate_decision_approve_requires_base_branch_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir)

            write_human_gate_handoff(
                run_root=run_root,
                issue_id="issue-id-123",
                issue_key="LIN-42",
                branch="feature/lin-42",
                worktree_path="/tmp/worktrees/lin-42",
                base_branch="",
                commit_sha="abc123",
                recommendation="review",
            )

            with self.assertRaisesRegex(ValueError, "Approved Human Gate decision requires non-empty handoff fields: base_branch"):
                write_human_gate_decision(
                    run_root=run_root,
                    status="done",
                    decision="approve",
                    issue_key="LIN-42",
                    note="Ship it",
                )

            self.assertFalse((run_root / "pr_handoff.md").exists())

    def test_write_human_gate_decision_does_not_write_pr_handoff_for_rejected_runs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir)

            write_human_gate_handoff(
                run_root=run_root,
                issue_id="issue-id-123",
                issue_key="LIN-42",
                branch="feature/lin-42",
                worktree_path="/tmp/worktrees/lin-42",
                base_branch="main",
                commit_sha="abc123",
                recommendation="review",
            )

            write_human_gate_decision(
                run_root=run_root,
                status="blocked",
                decision="reject",
                issue_key="LIN-42",
                note="Needs fixes",
            )

            self.assertFalse((run_root / "pr_handoff.md").exists())

    def test_write_pr_opened_persists_pr_url_and_artifact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir)

            write_human_gate_handoff(
                run_root=run_root,
                issue_id="issue-id-123",
                issue_key="LIN-42",
                branch="feature/lin-42",
                worktree_path="/tmp/worktrees/lin-42",
                base_branch="main",
                commit_sha="abc123",
                recommendation="review",
            )
            write_human_gate_decision(
                run_root=run_root,
                status="done",
                decision="approve",
                issue_key="LIN-42",
                note="Ship it",
            )

            write_pr_opened(run_root, "https://github.com/o/r/pull/42")

            status_payload = json.loads((run_root / "status.json").read_text())
            self.assertEqual(status_payload["human_gate"]["next_action"], "pr_opened")
            self.assertEqual(status_payload["pr"]["url"], "https://github.com/o/r/pull/42")
            self.assertIn("opened_at", status_payload["pr"])

            state_payload = json.loads((run_root / "state.json").read_text())
            self.assertEqual(state_payload["human_gate"]["next_action"], "pr_opened")
            self.assertEqual(state_payload["pr"]["url"], "https://github.com/o/r/pull/42")
            self.assertIn("opened_at", state_payload["pr"])

            self.assertTrue((run_root / "pr_opened.md").exists())
            markdown = (run_root / "pr_opened.md").read_text()
            self.assertIn("Issue: LIN-42", markdown)
            self.assertIn("PR URL: https://github.com/o/r/pull/42", markdown)
            self.assertIn("Opened At:", markdown)

    def test_write_pr_opened_rejects_empty_pr_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir)

            write_human_gate_handoff(
                run_root=run_root,
                issue_id="issue-id-123",
                issue_key="LIN-42",
                branch="feature/lin-42",
                worktree_path="/tmp/worktrees/lin-42",
                base_branch="main",
                commit_sha="abc123",
                recommendation="review",
            )
            write_human_gate_decision(
                run_root=run_root,
                status="done",
                decision="approve",
                issue_key="LIN-42",
                note="Ship it",
            )

            with self.assertRaisesRegex(ValueError, "PR URL must be non-empty"):
                write_pr_opened(run_root, "   ")

    def test_write_pr_opened_rejects_missing_ready_for_pr_approval_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir)

            write_human_gate_handoff(
                run_root=run_root,
                issue_id="issue-id-123",
                issue_key="LIN-42",
                branch="feature/lin-42",
                worktree_path="/tmp/worktrees/lin-42",
                base_branch="main",
                commit_sha="abc123",
                recommendation="review",
            )

            with self.assertRaisesRegex(
                ValueError,
                "write_pr_opened requires approved Human Gate decision with next_action == ready_for_pr",
            ):
                write_pr_opened(run_root, "https://github.com/o/r/pull/42")

    def test_write_pr_review_snapshot_rejects_missing_opened_pr_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir)

            write_human_gate_handoff(
                run_root=run_root,
                issue_id="issue-id-123",
                issue_key="LIN-42",
                branch="feature/lin-42",
                worktree_path="/tmp/worktrees/lin-42",
                base_branch="main",
                commit_sha="abc123",
                recommendation="review",
            )
            write_human_gate_decision(
                run_root=run_root,
                status="done",
                decision="approve",
                issue_key="LIN-42",
                note="Ship it",
            )

            with self.assertRaisesRegex(
                ValueError,
                "write_pr_review_snapshot requires an opened PR with non-empty URL and next_action == pr_opened",
            ):
                write_pr_review_snapshot(run_root, '{"comments":[],"reviews":[]}')

            self.assertFalse((run_root / "pr_review_comments.json").exists())
            self.assertFalse((run_root / "pr_review_summary.md").exists())

    def test_write_pr_review_snapshot_rejects_empty_pr_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir)

            write_human_gate_handoff(
                run_root=run_root,
                issue_id="issue-id-123",
                issue_key="LIN-42",
                branch="feature/lin-42",
                worktree_path="/tmp/worktrees/lin-42",
                base_branch="main",
                commit_sha="abc123",
                recommendation="review",
            )
            write_human_gate_decision(
                run_root=run_root,
                status="done",
                decision="approve",
                issue_key="LIN-42",
                note="Ship it",
            )
            write_pr_opened(run_root, "https://github.com/o/r/pull/42")

            payload = json.loads((run_root / "status.json").read_text())
            payload["pr"]["url"] = "   "
            (run_root / "status.json").write_text(json.dumps(payload, indent=2))

            with self.assertRaisesRegex(
                ValueError,
                "write_pr_review_snapshot requires an opened PR with non-empty URL and next_action == pr_opened",
            ):
                write_pr_review_snapshot(run_root, '{"comments":[],"reviews":[]}')

            self.assertFalse((run_root / "pr_review_comments.json").exists())
            self.assertFalse((run_root / "pr_review_summary.md").exists())

    def test_write_pr_review_snapshot_preserves_existing_pr_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir)

            write_human_gate_handoff(
                run_root=run_root,
                issue_id="issue-id-123",
                issue_key="LIN-42",
                branch="feature/lin-42",
                worktree_path="/tmp/worktrees/lin-42",
                base_branch="main",
                commit_sha="abc123",
                recommendation="review",
            )
            write_human_gate_decision(
                run_root=run_root,
                status="done",
                decision="approve",
                issue_key="LIN-42",
                note="Ship it",
            )
            write_pr_opened(run_root, "https://github.com/o/r/pull/42")

            original_opened_at = json.loads((run_root / "status.json").read_text())["pr"]["opened_at"]

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

            status_payload = json.loads((run_root / "status.json").read_text())
            self.assertEqual(status_payload["pr"]["url"], "https://github.com/o/r/pull/42")
            self.assertEqual(status_payload["pr"]["opened_at"], original_opened_at)
            self.assertEqual(status_payload["pr"]["review_comments_path"], "pr_review_comments.json")
            self.assertEqual(status_payload["pr"]["review_findings_path"], "pr_review_findings.json")
            self.assertEqual(status_payload["pr"]["review_triage_path"], "pr_review_triage.md")
            self.assertEqual(status_payload["pr"]["blocking_review_count"], 1)
            self.assertIn("review_fetched_at", status_payload["pr"])

            state_payload = json.loads((run_root / "state.json").read_text())
            self.assertEqual(state_payload["pr"]["url"], "https://github.com/o/r/pull/42")
            self.assertEqual(state_payload["pr"]["opened_at"], original_opened_at)
            self.assertEqual(state_payload["pr"]["review_comments_path"], "pr_review_comments.json")
            self.assertEqual(state_payload["pr"]["review_findings_path"], "pr_review_findings.json")
            self.assertEqual(state_payload["pr"]["review_triage_path"], "pr_review_triage.md")
            self.assertEqual(state_payload["pr"]["blocking_review_count"], 1)
            self.assertIn("review_fetched_at", state_payload["pr"])

            self.assertTrue((run_root / "pr_review_findings.json").exists())
            self.assertTrue((run_root / "pr_review_triage.md").exists())

    def test_write_pr_review_snapshot_persists_raw_payload_when_triage_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir)

            write_human_gate_handoff(
                run_root=run_root,
                issue_id="issue-id-123",
                issue_key="LIN-42",
                branch="feature/lin-42",
                worktree_path="/tmp/worktrees/lin-42",
                base_branch="main",
                commit_sha="abc123",
                recommendation="review",
            )
            write_human_gate_decision(
                run_root=run_root,
                status="done",
                decision="approve",
                issue_key="LIN-42",
                note="Ship it",
            )
            write_pr_opened(run_root, "https://github.com/o/r/pull/42")

            malformed_review_json = '{"comments": [}'

            with patch("symphony_runtime.run_store.summarize_review_payload", side_effect=ValueError("malformed review payload")):
                with self.assertRaisesRegex(ValueError, "malformed review payload"):
                    write_pr_review_snapshot(run_root, malformed_review_json)

            self.assertEqual((run_root / "pr_review_comments.json").read_text(), malformed_review_json)
            self.assertFalse((run_root / "pr_review_summary.md").exists())
            self.assertFalse((run_root / "pr_review_findings.json").exists())
            self.assertFalse((run_root / "pr_review_triage.md").exists())

            status_payload = json.loads((run_root / "status.json").read_text())
            self.assertNotIn("review_comments_path", status_payload["pr"])
            self.assertNotIn("review_findings_path", status_payload["pr"])
            self.assertNotIn("review_triage_path", status_payload["pr"])
            self.assertNotIn("blocking_review_count", status_payload["pr"])


if __name__ == "__main__":
    unittest.main()
