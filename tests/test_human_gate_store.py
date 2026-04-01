import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from symphony_runtime.human_gate_store import (
    HumanGateScanIssue,
    HumanGateScanResult,
    PrOpenedScanResult,
    list_pending_human_gate_runs,
    list_pr_opened_runs,
    list_ready_for_pr_runs,
    scan_pending_human_gate_runs,
    scan_pr_opened_runs,
    scan_ready_for_pr_runs,
    load_human_gate_context,
    load_human_gate_record,
    load_pr_opened_record,
    load_ready_for_pr_record,
    resolve_run_root,
)
from symphony_runtime.config import SymphonyConfig


class HumanGateStoreTests(unittest.TestCase):
    def _make_status_payload(self, **overrides):
        payload = {
            "status": "human_gate",
            "issue_id": "issue-id-123",
            "issue_key": "LIN-42",
            "branch": "feature/lin-42",
            "commit_sha": "abc123",
            "human_gate": {"decision_required": True, "decision_applied": False},
        }
        payload.update(overrides)
        return payload

    def _write_status(self, run_root: Path, **overrides):
        run_root.mkdir(parents=True)
        (run_root / "status.json").write_text(json.dumps(self._make_status_payload(**overrides)))

    def test_load_human_gate_context_reads_pending_issue_branch_and_commit_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir) / "lin-42"
            self._write_status(run_root)

            context = load_human_gate_context(run_root)

            self.assertEqual(context.issue_id, "issue-id-123")
            self.assertEqual(context.issue_key, "LIN-42")
            self.assertEqual(context.branch, "feature/lin-42")
            self.assertEqual(context.commit_sha, "abc123")

    def test_load_human_gate_context_reads_status_json_only_once(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir) / "lin-42"
            self._write_status(run_root)

            original_read_text = Path.read_text
            call_count = 0

            def counted_read_text(path_self, *args, **kwargs):
                nonlocal call_count
                if path_self == run_root / "status.json":
                    call_count += 1
                return original_read_text(path_self, *args, **kwargs)

            with patch.object(Path, "read_text", autospec=True, side_effect=counted_read_text):
                context = load_human_gate_context(run_root)

            self.assertEqual(context.issue_key, "LIN-42")
            self.assertEqual(call_count, 1)

    def test_load_human_gate_record_reads_pending_and_resolved_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir) / "lin-42"
            run_root.mkdir(parents=True)
            (run_root / "status.json").write_text(
                json.dumps(
                    {
                        "status": "done",
                        "issue_id": "issue-id-123",
                        "issue_key": "LIN-42",
                        "branch": "feature/lin-42",
                        "commit_sha": "abc123",
                        "human_gate": {
                            "recommendation": "review",
                            "decision": "approve",
                            "note": "Ship it",
                            "next_action": "ready_for_pr",
                            "decision_required": False,
                            "decision_applied": True,
                            "applied_at": "2026-03-15T10:00:00+00:00",
                        },
                    }
                )
            )

            record = load_human_gate_record(run_root)

            self.assertEqual(record.issue_key, "LIN-42")
            self.assertEqual(record.decision, "approve")
            self.assertEqual(record.note, "Ship it")
            self.assertEqual(record.next_action, "ready_for_pr")
            self.assertFalse(record.decision_required)
            self.assertTrue(record.decision_applied)

    def test_load_human_gate_record_rejects_missing_next_action_when_already_applied(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir) / "lin-42"
            run_root.mkdir(parents=True)
            (run_root / "status.json").write_text(
                json.dumps(
                    {
                        "status": "done",
                        "issue_id": "issue-id-123",
                        "issue_key": "LIN-42",
                        "branch": "feature/lin-42",
                        "commit_sha": "abc123",
                        "human_gate": {
                            "recommendation": "review",
                            "decision": "approve",
                            "decision_required": False,
                            "decision_applied": True,
                            "applied_at": "2026-03-15T10:00:00+00:00",
                        },
                    }
                )
            )

            with self.assertRaisesRegex(ValueError, "Missing or invalid human_gate.next_action"):
                load_human_gate_record(run_root)

    def test_load_human_gate_record_rejects_missing_decision_when_already_applied(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir) / "lin-42"
            run_root.mkdir(parents=True)
            (run_root / "status.json").write_text(
                json.dumps(
                    {
                        "status": "done",
                        "issue_id": "issue-id-123",
                        "issue_key": "LIN-42",
                        "branch": "feature/lin-42",
                        "commit_sha": "abc123",
                        "human_gate": {
                            "recommendation": "review",
                            "decision_required": False,
                            "decision_applied": True,
                            "applied_at": "2026-03-15T10:00:00+00:00",
                        },
                    }
                )
            )

            with self.assertRaisesRegex(ValueError, "Missing or invalid human_gate.decision"):
                load_human_gate_record(run_root)

    def test_load_ready_for_pr_record_requires_worktree_and_base_branch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir) / "lin-42"
            run_root.mkdir(parents=True)
            (run_root / "status.json").write_text(
                json.dumps(
                    {
                        "status": "done",
                        "issue_id": "issue-id-123",
                        "issue_key": "LIN-42",
                        "branch": "feature/lin-42",
                        "commit_sha": "abc123",
                        "worktree_path": "/tmp/worktree",
                        "base_branch": "main",
                        "human_gate": {
                            "decision": "approve",
                            "decision_required": False,
                            "decision_applied": True,
                            "applied_at": "2026-03-15T10:00:00+00:00",
                            "next_action": "ready_for_pr",
                        },
                    }
                )
            )

            record = load_ready_for_pr_record(run_root)

            self.assertEqual(record.base_branch, "main")
            self.assertEqual(record.worktree_path, Path("/tmp/worktree"))

    def test_load_ready_for_pr_record_rejects_missing_handoff_fields(self):
        required_fields = ("branch", "commit_sha", "worktree_path", "base_branch")

        for missing_field in required_fields:
            with self.subTest(missing_field=missing_field):
                with tempfile.TemporaryDirectory() as tmpdir:
                    run_root = Path(tmpdir) / "lin-42"
                    run_root.mkdir(parents=True)
                    payload = {
                        "status": "done",
                        "issue_id": "issue-id-123",
                        "issue_key": "LIN-42",
                        "branch": "feature/lin-42",
                        "commit_sha": "abc123",
                        "worktree_path": "/tmp/worktree",
                        "base_branch": "main",
                        "human_gate": {
                            "decision": "approve",
                            "decision_required": False,
                            "decision_applied": True,
                            "applied_at": "2026-03-15T10:00:00+00:00",
                            "next_action": "ready_for_pr",
                        },
                    }
                    payload.pop(missing_field)
                    (run_root / "status.json").write_text(json.dumps(payload))

                    with self.assertRaisesRegex(ValueError, missing_field):
                        load_ready_for_pr_record(run_root)

    def test_load_ready_for_pr_record_ignores_nested_handoff_fields_when_top_level_differs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir) / "lin-42"
            run_root.mkdir(parents=True)
            (run_root / "status.json").write_text(
                json.dumps(
                    {
                        "status": "done",
                        "issue_id": "issue-id-123",
                        "issue_key": "LIN-42",
                        "branch": "feature/lin-42",
                        "commit_sha": "abc123",
                        "worktree_path": "/tmp/top-level-worktree",
                        "base_branch": "release/main",
                        "human_gate": {
                            "decision": "approve",
                            "decision_required": False,
                            "decision_applied": True,
                            "applied_at": "2026-03-15T10:00:00+00:00",
                            "next_action": "ready_for_pr",
                            "worktree_path": "/tmp/nested-worktree",
                            "base_branch": "nested-main",
                        },
                    }
                )
            )

            record = load_ready_for_pr_record(run_root)

            self.assertEqual(record.worktree_path, Path("/tmp/top-level-worktree"))
            self.assertEqual(record.base_branch, "release/main")

    def test_load_ready_for_pr_record_rejects_pr_opened_next_action(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir) / "lin-42"
            run_root.mkdir(parents=True)
            (run_root / "status.json").write_text(
                json.dumps(
                    {
                        "status": "done",
                        "issue_id": "issue-id-123",
                        "issue_key": "LIN-42",
                        "branch": "feature/lin-42",
                        "commit_sha": "abc123",
                        "worktree_path": "/tmp/worktree",
                        "base_branch": "main",
                        "human_gate": {
                            "decision": "approve",
                            "decision_required": False,
                            "decision_applied": True,
                            "applied_at": "2026-03-15T10:00:00+00:00",
                            "next_action": "pr_opened",
                        },
                        "pr": {
                            "url": "https://github.com/o/r/pull/42",
                            "opened_at": "2026-03-15T10:15:00+00:00",
                        },
                    }
                )
            )

            with self.assertRaisesRegex(ValueError, "Expected ready_for_pr next action"):
                load_ready_for_pr_record(run_root)

    def test_load_pr_opened_record_reads_pr_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir) / "lin-42"
            run_root.mkdir(parents=True)
            (run_root / "status.json").write_text(
                json.dumps(
                    {
                        "status": "done",
                        "issue_id": "issue-id-123",
                        "issue_key": "LIN-42",
                        "branch": "feature/lin-42",
                        "commit_sha": "abc123",
                        "worktree_path": "/tmp/worktree",
                        "base_branch": "main",
                        "human_gate": {
                            "decision": "approve",
                            "decision_required": False,
                            "decision_applied": True,
                            "applied_at": "2026-03-15T10:00:00+00:00",
                            "next_action": "pr_opened",
                        },
                        "pr": {
                            "url": "https://github.com/o/r/pull/42",
                            "opened_at": "2026-03-15T10:05:00+00:00",
                        },
                    }
                )
            )

            record = load_pr_opened_record(run_root)

            self.assertEqual(record.issue_key, "LIN-42")
            self.assertEqual(record.pr_url, "https://github.com/o/r/pull/42")
            self.assertEqual(record.base_branch, "main")

    def test_load_pr_opened_record_rejects_missing_pr_metadata(self):
        for missing_field in ("url", "opened_at"):
            with self.subTest(missing_field=missing_field):
                with tempfile.TemporaryDirectory() as tmpdir:
                    run_root = Path(tmpdir) / "lin-42"
                    run_root.mkdir(parents=True)
                    payload = {
                        "status": "done",
                        "issue_id": "issue-id-123",
                        "issue_key": "LIN-42",
                        "branch": "feature/lin-42",
                        "commit_sha": "abc123",
                        "worktree_path": "/tmp/worktree",
                        "base_branch": "main",
                        "human_gate": {
                            "decision": "approve",
                            "decision_required": False,
                            "decision_applied": True,
                            "applied_at": "2026-03-15T10:00:00+00:00",
                            "next_action": "pr_opened",
                        },
                        "pr": {
                            "url": "https://github.com/o/r/pull/42",
                            "opened_at": "2026-03-15T10:05:00+00:00",
                        },
                    }
                    payload["pr"].pop(missing_field)
                    (run_root / "status.json").write_text(json.dumps(payload))

                    with self.assertRaisesRegex(ValueError, missing_field):
                        load_pr_opened_record(run_root)

    def test_load_human_gate_context_rejects_missing_or_invalid_human_gate_payload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir) / "lin-42"
            self._write_status(run_root, human_gate=None)

            with self.assertRaisesRegex(ValueError, "Missing or invalid human_gate payload"):
                load_human_gate_context(run_root)

    def test_load_human_gate_context_rejects_non_human_gate_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir) / "lin-42"
            self._write_status(run_root, status="running")

            with self.assertRaisesRegex(ValueError, "Expected pending Human Gate status"):
                load_human_gate_context(run_root)

    def test_load_human_gate_context_rejects_when_decision_not_required(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir) / "lin-42"
            self._write_status(run_root, human_gate={"decision_required": False, "decision_applied": False})

            with self.assertRaisesRegex(ValueError, "Expected pending Human Gate decision"):
                load_human_gate_context(run_root)

    def test_load_human_gate_context_rejects_when_decision_already_applied(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir) / "lin-42"
            self._write_status(
                run_root,
                human_gate={
                    "decision_required": True,
                    "decision_applied": True,
                    "decision": "approve",
                    "next_action": "ready_for_pr",
                    "applied_at": "2026-03-15T10:00:00+00:00",
                },
            )

            with self.assertRaisesRegex(ValueError, "Expected pending Human Gate decision"):
                load_human_gate_context(run_root)

    def test_resolve_run_root_accepts_run_id_under_config_runs_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SymphonyConfig(
                workspace_root=Path(tmpdir),
                config_root=Path(tmpdir) / "config",
                runs_root=Path(tmpdir) / "runs",
                worktrees_root=Path(tmpdir) / "worktrees",
            )
            run_root = config.runs_root / "lin-42"
            run_root.mkdir(parents=True)

            resolved = resolve_run_root(config, "lin-42")

            self.assertEqual(resolved, run_root.resolve())

    def test_resolve_run_root_rejects_relative_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SymphonyConfig(
                workspace_root=Path(tmpdir),
                config_root=Path(tmpdir) / "config",
                runs_root=Path(tmpdir) / "runs",
                worktrees_root=Path(tmpdir) / "worktrees",
            )

            with self.assertRaisesRegex(ValueError, "must stay within"):
                resolve_run_root(config, "../somewhere-else")

    def test_scan_pending_human_gate_runs_returns_valid_runs_and_invalid_run_warnings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SymphonyConfig(
                workspace_root=Path(tmpdir),
                config_root=Path(tmpdir) / "config",
                runs_root=Path(tmpdir) / "runs",
                worktrees_root=Path(tmpdir) / "worktrees",
            )
            config.runs_root.mkdir(parents=True)

            valid_run = config.runs_root / "lin-42"
            self._write_status(valid_run)

            invalid_run = config.runs_root / "lin-99"
            invalid_run.mkdir(parents=True)
            (invalid_run / "status.json").write_text("{not json")

            result = scan_pending_human_gate_runs(config)

            self.assertEqual(result.pending_runs, [load_human_gate_context(valid_run)])
            self.assertEqual(
                result.issues,
                [
                    HumanGateScanIssue(
                        run_root=invalid_run,
                        message="Expecting property name enclosed in double quotes: line 1 column 2 (char 1)",
                    )
                ],
            )

    def test_list_pending_human_gate_runs_keeps_returning_only_valid_pending_runs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SymphonyConfig(
                workspace_root=Path(tmpdir),
                config_root=Path(tmpdir) / "config",
                runs_root=Path(tmpdir) / "runs",
                worktrees_root=Path(tmpdir) / "worktrees",
            )
            config.runs_root.mkdir(parents=True)

            valid_run = config.runs_root / "lin-42"
            self._write_status(valid_run)

            invalid_run = config.runs_root / "lin-99"
            invalid_run.mkdir(parents=True)
            (invalid_run / "status.json").write_text("{not json")

            self.assertEqual(list_pending_human_gate_runs(config), [load_human_gate_context(valid_run)])

    def test_scan_ready_for_pr_runs_returns_valid_runs_and_invalid_run_warnings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SymphonyConfig(
                workspace_root=Path(tmpdir),
                config_root=Path(tmpdir) / "config",
                runs_root=Path(tmpdir) / "runs",
                worktrees_root=Path(tmpdir) / "worktrees",
            )
            config.runs_root.mkdir(parents=True)

            ready_run = config.runs_root / "lin-42"
            ready_run.mkdir()
            (ready_run / "status.json").write_text(
                json.dumps(
                    {
                        "status": "done",
                        "issue_id": "issue-id-123",
                        "issue_key": "LIN-42",
                        "branch": "feature/lin-42",
                        "commit_sha": "abc123",
                        "human_gate": {
                            "decision": "approve",
                            "decision_required": False,
                            "decision_applied": True,
                            "applied_at": "2026-03-15T10:00:00+00:00",
                            "next_action": "ready_for_pr",
                        },
                    }
                )
            )

            invalid_run = config.runs_root / "lin-99"
            invalid_run.mkdir()
            (invalid_run / "status.json").write_text("{not json")

            result = scan_ready_for_pr_runs(config)

            self.assertEqual(result.ready_runs, [load_human_gate_record(ready_run)])
            self.assertEqual(
                result.issues,
                [
                    HumanGateScanIssue(
                        run_root=invalid_run,
                        message="Expecting property name enclosed in double quotes: line 1 column 2 (char 1)",
                    )
                ],
            )

    def test_list_ready_for_pr_runs_returns_only_approved_done_runs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SymphonyConfig(
                workspace_root=Path(tmpdir),
                config_root=Path(tmpdir) / "config",
                runs_root=Path(tmpdir) / "runs",
                worktrees_root=Path(tmpdir) / "worktrees",
            )
            config.runs_root.mkdir(parents=True)

            ready_run = config.runs_root / "lin-42"
            ready_run.mkdir()
            (ready_run / "status.json").write_text(
                json.dumps(
                    {
                        "status": "done",
                        "issue_id": "issue-id-123",
                        "issue_key": "LIN-42",
                        "branch": "feature/lin-42",
                        "commit_sha": "abc123",
                        "human_gate": {
                            "decision": "approve",
                            "decision_required": False,
                            "decision_applied": True,
                            "applied_at": "2026-03-15T10:00:00+00:00",
                            "next_action": "ready_for_pr",
                        },
                    }
                )
            )

            contradictory_run = config.runs_root / "lin-43"
            contradictory_run.mkdir()
            (contradictory_run / "status.json").write_text(
                json.dumps(
                    {
                        "status": "blocked",
                        "issue_id": "issue-id-456",
                        "issue_key": "LIN-43",
                        "branch": "feature/lin-43",
                        "commit_sha": "def456",
                        "human_gate": {
                            "decision": "approve",
                            "decision_required": False,
                            "decision_applied": True,
                            "applied_at": "2026-03-15T10:05:00+00:00",
                            "next_action": "ready_for_pr",
                        },
                    }
                )
            )

            rejected_run = config.runs_root / "lin-44"
            rejected_run.mkdir()
            (rejected_run / "status.json").write_text(
                json.dumps(
                    {
                        "status": "blocked",
                        "issue_id": "issue-id-789",
                        "issue_key": "LIN-44",
                        "branch": "feature/lin-44",
                        "commit_sha": "ghi789",
                        "human_gate": {
                            "decision": "reject",
                            "decision_required": False,
                            "decision_applied": True,
                            "applied_at": "2026-03-15T10:10:00+00:00",
                            "next_action": "revise_and_rerun",
                        },
                    }
                )
            )

            records = list_ready_for_pr_runs(config)

            self.assertEqual([record.issue_key for record in records], ["LIN-42"])

    def test_scan_pr_opened_runs_returns_valid_runs_and_invalid_run_warnings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SymphonyConfig(
                workspace_root=Path(tmpdir),
                config_root=Path(tmpdir) / "config",
                runs_root=Path(tmpdir) / "runs",
                worktrees_root=Path(tmpdir) / "worktrees",
            )
            config.runs_root.mkdir(parents=True)

            opened_run = config.runs_root / "lin-42"
            opened_run.mkdir()
            (opened_run / "status.json").write_text(
                json.dumps(
                    {
                        "status": "done",
                        "issue_id": "issue-id-123",
                        "issue_key": "LIN-42",
                        "branch": "feature/lin-42",
                        "commit_sha": "abc123",
                        "worktree_path": "/tmp/worktree",
                        "base_branch": "main",
                        "human_gate": {
                            "decision": "approve",
                            "decision_required": False,
                            "decision_applied": True,
                            "applied_at": "2026-03-15T10:00:00+00:00",
                            "next_action": "pr_opened",
                        },
                        "pr": {
                            "url": "https://github.com/o/r/pull/42",
                            "opened_at": "2026-03-15T10:05:00+00:00",
                        },
                    }
                )
            )

            ready_run = config.runs_root / "lin-43"
            ready_run.mkdir()
            (ready_run / "status.json").write_text(
                json.dumps(
                    {
                        "status": "done",
                        "issue_id": "issue-id-456",
                        "issue_key": "LIN-43",
                        "branch": "feature/lin-43",
                        "commit_sha": "def456",
                        "worktree_path": "/tmp/worktree-2",
                        "base_branch": "main",
                        "human_gate": {
                            "decision": "approve",
                            "decision_required": False,
                            "decision_applied": True,
                            "applied_at": "2026-03-15T10:10:00+00:00",
                            "next_action": "ready_for_pr",
                        },
                    }
                )
            )

            invalid_run = config.runs_root / "lin-44"
            invalid_run.mkdir()
            (invalid_run / "status.json").write_text(
                json.dumps(
                    {
                        "status": "done",
                        "issue_id": "issue-id-789",
                        "issue_key": "LIN-44",
                        "branch": "feature/lin-44",
                        "commit_sha": "ghi789",
                        "worktree_path": "/tmp/worktree-3",
                        "base_branch": "main",
                        "human_gate": {
                            "decision": "approve",
                            "decision_required": False,
                            "decision_applied": True,
                            "applied_at": "2026-03-15T10:20:00+00:00",
                            "next_action": "pr_opened",
                        },
                        "pr": {
                            "opened_at": "2026-03-15T10:25:00+00:00",
                        },
                    }
                )
            )

            result = scan_pr_opened_runs(config)

            self.assertEqual(
                result,
                PrOpenedScanResult(
                    records=[load_pr_opened_record(opened_run)],
                    issues=[
                        HumanGateScanIssue(
                            run_root=ready_run,
                            message=f"Expected pr_opened next action in {ready_run / 'status.json'}",
                        ),
                        HumanGateScanIssue(
                            run_root=invalid_run,
                            message=f"Missing or invalid pr fields in {invalid_run / 'status.json'}: url",
                        ),
                    ],
                ),
            )

    def test_list_pr_opened_runs_returns_only_opened_pr_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SymphonyConfig(
                workspace_root=Path(tmpdir),
                config_root=Path(tmpdir) / "config",
                runs_root=Path(tmpdir) / "runs",
                worktrees_root=Path(tmpdir) / "worktrees",
            )
            config.runs_root.mkdir(parents=True)

            opened_run = config.runs_root / "lin-42"
            opened_run.mkdir()
            (opened_run / "status.json").write_text(
                json.dumps(
                    {
                        "status": "done",
                        "issue_id": "issue-id-123",
                        "issue_key": "LIN-42",
                        "branch": "feature/lin-42",
                        "commit_sha": "abc123",
                        "worktree_path": "/tmp/worktree",
                        "base_branch": "main",
                        "human_gate": {
                            "decision": "approve",
                            "decision_required": False,
                            "decision_applied": True,
                            "applied_at": "2026-03-15T10:00:00+00:00",
                            "next_action": "pr_opened",
                        },
                        "pr": {
                            "url": "https://github.com/o/r/pull/42",
                            "opened_at": "2026-03-15T10:05:00+00:00",
                        },
                    }
                )
            )

            invalid_run = config.runs_root / "lin-44"
            invalid_run.mkdir()
            (invalid_run / "status.json").write_text("{not json")

            records = list_pr_opened_runs(config)

            self.assertEqual([record.issue_key for record in records], ["LIN-42"])

    def test_resolve_run_root_accepts_absolute_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SymphonyConfig(
                workspace_root=Path(tmpdir),
                config_root=Path(tmpdir) / "config",
                runs_root=Path(tmpdir) / "runs",
                worktrees_root=Path(tmpdir) / "worktrees",
            )
            absolute_run_root = Path(tmpdir) / "external-run"

            resolved = resolve_run_root(config, str(absolute_run_root))

            self.assertEqual(resolved, absolute_run_root)
