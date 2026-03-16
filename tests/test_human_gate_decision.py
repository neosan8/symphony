import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from symphony_runtime.config import SymphonyConfig
from symphony_runtime.daemon import SymphonyRuntime
from symphony_runtime.run_store import initialize_run_state, write_human_gate_handoff


class HumanGateDecisionTests(unittest.TestCase):
    def make_runtime(self, tmpdir: str) -> SymphonyRuntime:
        runtime = SymphonyRuntime(
            config=SymphonyConfig(
                workspace_root=Path(tmpdir),
                config_root=Path(tmpdir) / "config",
                runs_root=Path(tmpdir) / "runs",
                worktrees_root=Path(tmpdir) / "worktrees",
            )
        )
        runtime.linear_client = Mock()
        runtime.sync_status = Mock(return_value=True)
        runtime.get_linear_client().add_comment.return_value = True
        return runtime

    def make_run_root(self, tmpdir: str) -> Path:
        run_root = Path(tmpdir) / "runs" / "lin-42"
        initialize_run_state(run_root, "LIN-42", "demo-repo")
        return run_root

    def read_json(self, path: Path) -> dict:
        return json.loads(path.read_text())

    def test_apply_human_gate_approval_marks_done_comments_and_persists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = self.make_runtime(tmpdir)
            run_root = self.make_run_root(tmpdir)
            (run_root / "status.json").write_text(json.dumps({
                "status": "human_gate",
                "issue_id": "issue-id-123",
                "issue_key": "LIN-42",
                "branch": "feature/lin-42",
                "worktree_path": "/tmp/worktrees/lin-42",
                "base_branch": "main",
                "commit_sha": "abc123",
                "human_gate": {
                    "recommendation": "review",
                    "decision_required": True,
                    "decision_applied": False,
                },
            }))

            runtime.apply_human_gate_decision(
                issue_id="issue-id-123",
                issue_key="LIN-42",
                decision="approve",
                note="Ship it",
                run_root=run_root,
            )

            runtime.sync_status.assert_called_once_with("issue-id-123", "Done")
            runtime.get_linear_client().add_comment.assert_called_once()

            status_payload = self.read_json(run_root / "status.json")
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

            state_payload = self.read_json(run_root / "state.json")
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
            self.assertEqual(state_payload["repo_key"], "demo-repo")
            self.assertIn("updated_at", state_payload)
            self.assertTrue((run_root / "human_gate_decision.md").exists())
            decision_markdown = (run_root / "human_gate_decision.md").read_text()
            self.assertIn("Issue: LIN-42", decision_markdown)
            self.assertIn("Decision: approve", decision_markdown)
            self.assertIn("Note: Ship it", decision_markdown)
            self.assertIn("Next Action: ready_for_pr", decision_markdown)
            self.assertIn("Applied At:", decision_markdown)
            self.assertTrue((run_root / "pr_handoff.md").exists())
            pr_handoff = (run_root / "pr_handoff.md").read_text()
            self.assertIn("Issue: LIN-42", pr_handoff)
            self.assertIn("Branch: feature/lin-42", pr_handoff)
            self.assertIn("Worktree: /tmp/worktrees/lin-42", pr_handoff)
            self.assertIn("Base Branch: main", pr_handoff)
            self.assertIn("Commit: abc123", pr_handoff)
            self.assertIn("Note: Ship it", pr_handoff)
            self.assertIn("Next Action: ready_for_pr", pr_handoff)

    def test_apply_human_gate_rejection_marks_blocked_comments_and_persists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = self.make_runtime(tmpdir)
            run_root = self.make_run_root(tmpdir)

            runtime.apply_human_gate_decision(
                issue_id="issue-id-123",
                issue_key="LIN-42",
                decision="reject",
                note="Needs fixes",
                run_root=run_root,
            )

            runtime.sync_status.assert_called_once_with("issue-id-123", "Blocked")
            runtime.get_linear_client().add_comment.assert_called_once()
            comment_body = runtime.get_linear_client().add_comment.call_args.args[1]
            self.assertIn("rejected", comment_body)
            self.assertIn("Needs fixes", comment_body)

            status_payload = self.read_json(run_root / "status.json")
            self.assertEqual(status_payload["status"], "blocked")
            self.assertEqual(status_payload["human_gate"]["decision"], "reject")
            self.assertEqual(status_payload["human_gate"]["note"], "Needs fixes")
            self.assertEqual(status_payload["human_gate"]["next_action"], "revise_and_rerun")
            self.assertFalse(status_payload["human_gate"]["decision_required"])
            self.assertTrue(status_payload["human_gate"]["decision_applied"])
            self.assertIn("applied_at", status_payload["human_gate"])

            state_payload = self.read_json(run_root / "state.json")
            self.assertEqual(state_payload["status"], "blocked")
            self.assertEqual(state_payload["human_gate"]["decision"], "reject")
            self.assertEqual(state_payload["human_gate"]["note"], "Needs fixes")
            self.assertEqual(state_payload["human_gate"]["next_action"], "revise_and_rerun")
            self.assertFalse(state_payload["human_gate"]["decision_required"])
            self.assertTrue(state_payload["human_gate"]["decision_applied"])
            self.assertIn("applied_at", state_payload["human_gate"])
            self.assertFalse((run_root / "pr_handoff.md").exists())

    def test_apply_human_gate_approval_requires_preserved_handoff_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = self.make_runtime(tmpdir)
            run_root = self.make_run_root(tmpdir)
            before_state = self.read_json(run_root / "state.json")
            (run_root / "status.json").write_text(json.dumps({
                "status": "human_gate",
                "issue_id": "issue-id-123",
                "issue_key": "LIN-42",
                "human_gate": {
                    "recommendation": "review",
                    "decision_required": True,
                    "decision_applied": False,
                },
            }))

            with self.assertRaisesRegex(ValueError, "Approved Human Gate decision requires non-empty handoff fields: branch, commit_sha, worktree_path, base_branch"):
                runtime.apply_human_gate_decision(
                    issue_id="issue-id-123",
                    issue_key="LIN-42",
                    decision="approve",
                    note="Ship it",
                    run_root=run_root,
                )

            runtime.get_linear_client().add_comment.assert_called_once()
            runtime.sync_status.assert_called_once_with("issue-id-123", "Done")
            self.assertEqual(self.read_json(run_root / "state.json"), before_state)
            self.assertFalse((run_root / "pr_handoff.md").exists())

    def test_apply_human_gate_approval_marks_next_action_ready_for_pr(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = self.make_runtime(tmpdir)
            run_root = self.make_run_root(tmpdir)
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

            runtime.apply_human_gate_decision(
                issue_id="issue-id-123",
                issue_key="LIN-42",
                decision="approve",
                note="Ship it",
                run_root=run_root,
            )

            payload = json.loads((run_root / "status.json").read_text())
            self.assertEqual(payload["human_gate"]["next_action"], "ready_for_pr")

    def test_apply_human_gate_rejection_marks_next_action_revise(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = self.make_runtime(tmpdir)
            run_root = self.make_run_root(tmpdir)

            runtime.apply_human_gate_decision(
                issue_id="issue-id-123",
                issue_key="LIN-42",
                decision="reject",
                note="Needs fixes",
                run_root=run_root,
            )

            payload = json.loads((run_root / "status.json").read_text())
            self.assertEqual(payload["human_gate"]["next_action"], "revise_and_rerun")

    def test_apply_human_gate_decision_writes_human_readable_decision_artifact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = self.make_runtime(tmpdir)
            run_root = self.make_run_root(tmpdir)
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

            runtime.apply_human_gate_decision(
                issue_id="issue-id-123",
                issue_key="LIN-42",
                decision="approve",
                note="Ship it",
                run_root=run_root,
            )

            self.assertTrue((run_root / "human_gate_decision.md").exists())
            self.assertIn(
                "Decision: approve",
                (run_root / "human_gate_decision.md").read_text(),
            )

    def test_apply_human_gate_invalid_decision_raises_value_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = self.make_runtime(tmpdir)
            run_root = self.make_run_root(tmpdir)
            before_state = self.read_json(run_root / "state.json")

            with self.assertRaisesRegex(ValueError, "Unknown Human Gate decision"):
                runtime.apply_human_gate_decision(
                    issue_id="issue-id-123",
                    issue_key="LIN-42",
                    decision="maybe",
                    note="Nope",
                    run_root=run_root,
                )

            runtime.get_linear_client().add_comment.assert_not_called()
            runtime.sync_status.assert_not_called()
            self.assertFalse((run_root / "status.json").exists())
            self.assertEqual(self.read_json(run_root / "state.json"), before_state)

    def test_apply_human_gate_add_comment_failure_raises_and_does_not_persist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = self.make_runtime(tmpdir)
            run_root = self.make_run_root(tmpdir)
            before_state = self.read_json(run_root / "state.json")
            runtime.get_linear_client().add_comment.return_value = False

            with self.assertRaisesRegex(RuntimeError, "Failed to sync Human Gate approve comment"):
                runtime.apply_human_gate_decision(
                    issue_id="issue-id-123",
                    issue_key="LIN-42",
                    decision="approve",
                    note="Ship it",
                    run_root=run_root,
                )

            runtime.sync_status.assert_not_called()
            self.assertFalse((run_root / "status.json").exists())
            self.assertEqual(self.read_json(run_root / "state.json"), before_state)

    def test_apply_human_gate_status_sync_failure_raises_and_does_not_persist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = self.make_runtime(tmpdir)
            run_root = self.make_run_root(tmpdir)
            before_state = self.read_json(run_root / "state.json")
            runtime.sync_status.return_value = False

            with self.assertRaisesRegex(RuntimeError, "Failed to sync Human Gate reject status Blocked"):
                runtime.apply_human_gate_decision(
                    issue_id="issue-id-123",
                    issue_key="LIN-42",
                    decision="reject",
                    note="Needs fixes",
                    run_root=run_root,
                )

            runtime.get_linear_client().add_comment.assert_called_once()
            runtime.sync_status.assert_called_once_with("issue-id-123", "Blocked")
            self.assertFalse((run_root / "status.json").exists())
            self.assertEqual(self.read_json(run_root / "state.json"), before_state)

    def test_apply_human_gate_decision_from_run_loads_context_and_applies_decision(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = SymphonyRuntime(
                config=SymphonyConfig(
                    workspace_root=Path(tmpdir),
                    config_root=Path(tmpdir) / "config",
                    runs_root=Path(tmpdir) / "runs",
                    worktrees_root=Path(tmpdir) / "worktrees",
                )
            )
            run_root = (runtime.config.runs_root / "lin-42").resolve()
            run_root.mkdir(parents=True)
            (run_root / "status.json").write_text(json.dumps({
                "status": "human_gate",
                "issue_id": "issue-id-123",
                "issue_key": "LIN-42",
                "branch": "feature/lin-42",
                "commit_sha": "abc123",
                "human_gate": {"decision_required": True, "decision_applied": False},
            }))
            runtime.apply_human_gate_decision = Mock(return_value=None)

            runtime.apply_human_gate_decision_from_run("lin-42", "approve", "Ship it")

            runtime.apply_human_gate_decision.assert_called_once_with(
                issue_id="issue-id-123",
                issue_key="LIN-42",
                decision="approve",
                note="Ship it",
                run_root=run_root,
            )


if __name__ == "__main__":
    unittest.main()
