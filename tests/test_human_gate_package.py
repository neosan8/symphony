import json
import tempfile
import unittest
from pathlib import Path

from symphony_runtime.config import SymphonyConfig
from symphony_runtime.daemon import SymphonyRuntime
from symphony_runtime.human_gate_package import build_human_gate_package, render_human_gate_package_markdown


class HumanGatePackageTests(unittest.TestCase):
    def test_build_human_gate_package_includes_execution_and_review_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir)
            status_payload = {
                "status": "done",
                "issue_id": "issue-id-123",
                "issue_key": "LIN-42",
                "branch": "feature/lin-42",
                "commit_sha": "abc123",
                "summary_path": "summary.md",
                "verification_path": "verification.md",
                "review_path": "review.md",
                "human_gate": {
                    "recommendation": "review",
                    "decision": "approve",
                    "note": "Ship it",
                    "next_action": "pr_opened",
                    "decision_required": False,
                    "decision_applied": True,
                    "applied_at": "2026-03-16T10:00:00+00:00",
                },
                "pr": {
                    "url": "https://github.com/o/r/pull/42",
                    "review_diff_path": "pr_review_diff.json",
                    "blocking_review_count": 0,
                    "review_findings_path": "pr_review_findings.json",
                    "newly_introduced_findings_count": 0,
                    "resolved_findings_count": 1,
                    "review_acknowledgement": {
                        "state": "addressed",
                        "path": "pr_review_acknowledgement.md",
                        "acknowledged_at": "2026-03-16T10:05:00+00:00",
                    },
                },
            }
            state_payload = {
                "status": "done",
                "issue_key": "LIN-42",
                "summary_path": "summary.md",
                "verification_path": "verification.md",
                "review_path": "review.md",
                "pr": {
                    "review_findings_path": "pr_review_findings.json",
                    "review_diff_path": "pr_review_diff.json",
                },
            }
            (run_root / "status.json").write_text(json.dumps(status_payload, indent=2))
            (run_root / "state.json").write_text(json.dumps(state_payload, indent=2))
            (run_root / "summary.md").write_text("# Summary\n")
            (run_root / "verification.md").write_text("# Verification\n")
            (run_root / "review.md").write_text("# Review\n")
            (run_root / "pr_review_diff.json").write_text(json.dumps({
                "newly_introduced_count": 0,
                "resolved_count": 1,
            }, indent=2))
            (run_root / "pr_review_findings.json").write_text(json.dumps({
                "blocking_count": 0,
                "unresolved_findings": [],
            }, indent=2))
            (run_root / "pr_review_acknowledgement.md").write_text("# Ack\n")

            package = build_human_gate_package(run_root)

            self.assertEqual(package["issue_key"], "LIN-42")
            self.assertEqual(package["summary_path"], "summary.md")
            self.assertEqual(package["verification_path"], "verification.md")
            self.assertEqual(package["review_path"], "review.md")
            self.assertEqual(package["blocking_review_count"], 0)
            self.assertEqual(package["unresolved_findings_count"], 0)
            self.assertEqual(package["newly_introduced_findings_count"], 0)
            self.assertEqual(package["resolved_findings_count"], 1)
            self.assertEqual(package["acknowledgement_state"], "addressed")
            self.assertEqual(package["acknowledgement_path"], "pr_review_acknowledgement.md")
            self.assertEqual(package["review_diff_path"], "pr_review_diff.json")

            markdown = render_human_gate_package_markdown(package)
            self.assertIn("Decision: approve", markdown)
            self.assertIn("Next Action: pr_opened", markdown)
            self.assertIn("Blocking Review Count: 0", markdown)
            self.assertIn("Unresolved Findings Count: 0", markdown)
            self.assertIn("Resolved Findings Count: 1", markdown)
            self.assertIn("Acknowledgement State: addressed", markdown)
            self.assertIn("Acknowledgement Path: pr_review_acknowledgement.md", markdown)
            self.assertIn("Review Diff Path: pr_review_diff.json", markdown)

    def test_build_human_gate_package_requires_status_artifact_pointers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir)
            status_payload = {
                "status": "human_gate",
                "issue_key": "LIN-42",
                "summary_path": "summary.md",
                "verification_path": "verification.md",
                "human_gate": {
                    "recommendation": "review",
                    "decision_required": True,
                    "decision_applied": False,
                },
            }
            state_payload = {
                "status": "human_gate",
                "issue_key": "LIN-42",
                "summary_path": "summary.md",
                "verification_path": "verification.md",
                "review_path": "review.md",
            }
            (run_root / "status.json").write_text(json.dumps(status_payload, indent=2))
            (run_root / "state.json").write_text(json.dumps(state_payload, indent=2))
            (run_root / "summary.md").write_text("# Summary\n")
            (run_root / "verification.md").write_text("# Verification\n")

            with self.assertRaisesRegex(ValueError, "Missing or invalid review_path in"):
                build_human_gate_package(run_root)


    def test_build_human_gate_package_fails_on_inconsistent_required_artifact_pointers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir)
            status_payload = {
                "status": "human_gate",
                "issue_key": "LIN-42",
                "summary_path": "summary.md",
                "verification_path": "verification.md",
                "review_path": "review.md",
                "human_gate": {
                    "recommendation": "review",
                    "decision_required": True,
                    "decision_applied": False,
                },
            }
            state_payload = {
                "status": "human_gate",
                "issue_key": "LIN-42",
                "summary_path": "different-summary.md",
                "verification_path": "verification.md",
                "review_path": "review.md",
            }
            (run_root / "status.json").write_text(json.dumps(status_payload, indent=2))
            (run_root / "state.json").write_text(json.dumps(state_payload, indent=2))
            (run_root / "summary.md").write_text("# Summary\n")
            (run_root / "different-summary.md").write_text("# Other Summary\n")
            (run_root / "verification.md").write_text("# Verification\n")
            (run_root / "review.md").write_text("# Review\n")

            with self.assertRaisesRegex(ValueError, "Required artifact metadata mismatch"):
                build_human_gate_package(run_root)

    def test_build_human_gate_package_requires_referenced_required_artifacts_to_exist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir)
            status_payload = {
                "status": "human_gate",
                "issue_key": "LIN-42",
                "summary_path": "summary.md",
                "verification_path": "verification.md",
                "review_path": "review.md",
                "human_gate": {
                    "recommendation": "review",
                    "decision_required": True,
                    "decision_applied": False,
                },
            }
            state_payload = {
                "status": "human_gate",
                "issue_key": "LIN-42",
                "summary_path": "summary.md",
                "verification_path": "verification.md",
                "review_path": "review.md",
            }
            (run_root / "status.json").write_text(json.dumps(status_payload, indent=2))
            (run_root / "state.json").write_text(json.dumps(state_payload, indent=2))
            (run_root / "summary.md").write_text("# Summary\n")
            (run_root / "verification.md").write_text("# Verification\n")

            with self.assertRaisesRegex(ValueError, "Missing required artifact referenced by"):
                build_human_gate_package(run_root)

    def test_build_human_gate_package_fails_on_inconsistent_review_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir)
            status_payload = {
                "status": "done",
                "issue_key": "LIN-42",
                "summary_path": "summary.md",
                "verification_path": "verification.md",
                "review_path": "review.md",
                "human_gate": {
                    "recommendation": "review",
                    "decision_required": False,
                    "decision_applied": True,
                },
                "pr": {
                    "url": "https://github.com/o/r/pull/42",
                    "review_findings_path": "missing_review_findings.json",
                },
            }
            state_payload = {
                "status": "done",
                "issue_key": "LIN-42",
                "summary_path": "summary.md",
                "verification_path": "verification.md",
                "review_path": "review.md",
                "pr": {
                    "review_findings_path": "different_review_findings.json",
                },
            }
            (run_root / "status.json").write_text(json.dumps(status_payload, indent=2))
            (run_root / "state.json").write_text(json.dumps(state_payload, indent=2))
            (run_root / "summary.md").write_text("# Summary\n")
            (run_root / "verification.md").write_text("# Verification\n")
            (run_root / "review.md").write_text("# Review\n")

            with self.assertRaisesRegex(ValueError, "PR review metadata mismatch"):
                build_human_gate_package(run_root)

    def test_get_human_gate_package_from_run_returns_compact_cli_payload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir)
            config = SymphonyConfig(
                workspace_root=workspace_root,
                config_root=workspace_root / "config",
                runs_root=workspace_root / "runs",
                worktrees_root=workspace_root / "worktrees",
            )
            config.runs_root.mkdir(parents=True)
            run_root = config.runs_root / "lin-42"
            run_root.mkdir()

            status_payload = {
                "status": "done",
                "issue_id": "issue-id-123",
                "issue_key": "LIN-42",
                "branch": "feature/lin-42",
                "commit_sha": "abc123",
                "summary_path": "summary.md",
                "verification_path": "verification.md",
                "review_path": "review.md",
                "human_gate": {
                    "recommendation": "review",
                    "decision": "approve",
                    "note": "Ship it",
                    "next_action": "pr_opened",
                    "decision_required": False,
                    "decision_applied": True,
                    "package_json_path": "human_gate_package.json",
                    "package_markdown_path": "human_gate_package.md",
                },
                "pr": {
                    "url": "https://github.com/o/r/pull/42",
                    "review_findings_path": "pr_review_findings.json",
                    "review_diff_path": "pr_review_diff.json",
                    "blocking_review_count": 0,
                    "newly_introduced_findings_count": 0,
                    "resolved_findings_count": 1,
                    "review_acknowledgement": {
                        "state": "addressed",
                        "path": "pr_review_acknowledgement.md",
                    },
                },
            }
            state_payload = {
                "status": "done",
                "issue_key": "LIN-42",
                "summary_path": "summary.md",
                "verification_path": "verification.md",
                "review_path": "review.md",
                "human_gate": {
                    "package_json_path": "human_gate_package.json",
                    "package_markdown_path": "human_gate_package.md",
                },
                "pr": {
                    "review_findings_path": "pr_review_findings.json",
                    "review_diff_path": "pr_review_diff.json",
                },
            }
            (run_root / "status.json").write_text(json.dumps(status_payload, indent=2))
            (run_root / "state.json").write_text(json.dumps(state_payload, indent=2))
            (run_root / "summary.md").write_text("# Summary\n")
            (run_root / "verification.md").write_text("# Verification\n")
            (run_root / "review.md").write_text("# Review\n")
            (run_root / "pr_review_diff.json").write_text(json.dumps({"newly_introduced_count": 0, "resolved_count": 1}, indent=2))
            (run_root / "pr_review_findings.json").write_text(json.dumps({"blocking_count": 0, "unresolved_findings": []}, indent=2))
            (run_root / "pr_review_acknowledgement.md").write_text("# Ack\n")
            package_payload = build_human_gate_package(run_root)
            (run_root / "human_gate_package.json").write_text(json.dumps(package_payload, indent=2))
            (run_root / "human_gate_package.md").write_text("# Package\n")

            runtime = SymphonyRuntime(config=config)
            package = runtime.get_human_gate_package_from_run("lin-42")

            self.assertEqual(package["run_ref"], "lin-42")
            self.assertEqual(package["issue_key"], "LIN-42")
            self.assertEqual(package["branch"], "feature/lin-42")
            self.assertEqual(package["recommendation"], "review")
            self.assertEqual(package["verification_path"], str((run_root / "verification.md").resolve()))
            self.assertEqual(package["review_path"], str((run_root / "review.md").resolve()))
            self.assertEqual(package["blocking_review_count"], 0)
            self.assertEqual(package["unresolved_findings_count"], 0)
            self.assertEqual(package["acknowledgement_state"], "addressed")
            self.assertEqual(package["package_json_path"], str((run_root / "human_gate_package.json").resolve()))
            self.assertEqual(package["package_markdown_path"], str((run_root / "human_gate_package.md").resolve()))


    def test_get_human_gate_package_from_run_rejects_package_path_outside_run_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir)
            config = SymphonyConfig(
                workspace_root=workspace_root,
                config_root=workspace_root / "config",
                runs_root=workspace_root / "runs",
                worktrees_root=workspace_root / "worktrees",
            )
            config.runs_root.mkdir(parents=True)
            run_root = config.runs_root / "lin-42"
            run_root.mkdir()

            status_payload = {
                "status": "done",
                "issue_id": "issue-id-123",
                "issue_key": "LIN-42",
                "branch": "feature/lin-42",
                "commit_sha": "abc123",
                "summary_path": "summary.md",
                "verification_path": "verification.md",
                "review_path": "review.md",
                "human_gate": {
                    "recommendation": "review",
                    "decision_required": False,
                    "decision_applied": True,
                    "package_json_path": "../escape.json",
                    "package_markdown_path": "human_gate_package.md",
                },
            }
            state_payload = {
                "status": "done",
                "issue_key": "LIN-42",
                "summary_path": "summary.md",
                "verification_path": "verification.md",
                "review_path": "review.md",
                "human_gate": {
                    "package_json_path": "../escape.json",
                    "package_markdown_path": "human_gate_package.md",
                },
            }
            (run_root / "status.json").write_text(json.dumps(status_payload, indent=2))
            (run_root / "state.json").write_text(json.dumps(state_payload, indent=2))
            (run_root / "summary.md").write_text("# Summary\n")
            (run_root / "verification.md").write_text("# Verification\n")
            (run_root / "review.md").write_text("# Review\n")
            (run_root / "human_gate_package.md").write_text("# Package\n")
            (config.runs_root / "escape.json").write_text("{}")

            runtime = SymphonyRuntime(config=config)
            with self.assertRaisesRegex(ValueError, "Invalid package_json_path"):
                runtime.get_human_gate_package_from_run("lin-42")

    def test_get_human_gate_package_from_run_rejects_missing_package_artifact_pointer(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir)
            config = SymphonyConfig(
                workspace_root=workspace_root,
                config_root=workspace_root / "config",
                runs_root=workspace_root / "runs",
                worktrees_root=workspace_root / "worktrees",
            )
            config.runs_root.mkdir(parents=True)
            run_root = config.runs_root / "lin-42"
            run_root.mkdir()

            status_payload = {
                "status": "done",
                "issue_id": "issue-id-123",
                "issue_key": "LIN-42",
                "branch": "feature/lin-42",
                "commit_sha": "abc123",
                "summary_path": "summary.md",
                "verification_path": "verification.md",
                "review_path": "review.md",
                "human_gate": {
                    "recommendation": "review",
                    "decision_required": False,
                    "decision_applied": True,
                    "package_markdown_path": "human_gate_package.md",
                },
            }
            state_payload = {
                "status": "done",
                "issue_key": "LIN-42",
                "summary_path": "summary.md",
                "verification_path": "verification.md",
                "review_path": "review.md",
                "human_gate": {
                    "package_markdown_path": "human_gate_package.md",
                },
            }
            (run_root / "status.json").write_text(json.dumps(status_payload, indent=2))
            (run_root / "state.json").write_text(json.dumps(state_payload, indent=2))
            (run_root / "summary.md").write_text("# Summary\n")
            (run_root / "verification.md").write_text("# Verification\n")
            (run_root / "review.md").write_text("# Review\n")
            (run_root / "human_gate_package.md").write_text("# Package\n")

            runtime = SymphonyRuntime(config=config)
            with self.assertRaisesRegex(ValueError, "package_json_path"):
                runtime.get_human_gate_package_from_run("lin-42")


if __name__ == "__main__":
    unittest.main()
