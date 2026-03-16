import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from symphony_runtime import cli
from symphony_runtime.config import SymphonyConfig
from symphony_runtime.daemon import SymphonyRuntime


class RuntimeCliTests(unittest.TestCase):
    @patch("symphony_runtime.cli.build_runtime")
    def test_human_gate_apply_command_delegates_to_runtime(self, build_runtime):
        runtime = Mock(spec=SymphonyRuntime)
        build_runtime.return_value = runtime

        exit_code = cli.main([
            "human-gate",
            "apply",
            "--run",
            "lin-42",
            "--decision",
            "approve",
            "--note",
            "Ship it",
        ])

        self.assertEqual(exit_code, 0)
        runtime.apply_human_gate_decision_from_run.assert_called_once_with(
            "lin-42", "approve", "Ship it"
        )

    def test_human_gate_list_prints_exact_tab_separated_output_for_pending_runs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SymphonyConfig(
                workspace_root=Path(tmpdir),
                config_root=Path(tmpdir) / "config",
                runs_root=Path(tmpdir) / "runs",
                worktrees_root=Path(tmpdir) / "worktrees",
            )
            config.runs_root.mkdir(parents=True)

            pending_run = config.runs_root / "lin-42"
            pending_run.mkdir()
            (pending_run / "status.json").write_text(
                json.dumps(
                    {
                        "status": "human_gate",
                        "issue_id": "issue-id-123",
                        "issue_key": "LIN-42",
                        "branch": "feature/lin-42",
                        "commit_sha": "abc123",
                        "human_gate": {
                            "decision_required": True,
                            "decision_applied": False,
                        },
                    }
                )
            )

            applied_run = config.runs_root / "lin-43"
            applied_run.mkdir()
            (applied_run / "status.json").write_text(
                json.dumps(
                    {
                        "status": "human_gate",
                        "issue_id": "issue-id-456",
                        "issue_key": "LIN-43",
                        "branch": "feature/lin-43",
                        "commit_sha": "def456",
                        "human_gate": {
                            "decision_required": True,
                            "decision_applied": True,
                        },
                    }
                )
            )

            ready_run = config.runs_root / "lin-44"
            ready_run.mkdir()
            (ready_run / "status.json").write_text(json.dumps({"status": "done"}))

            runtime = Mock(spec=SymphonyRuntime)
            runtime.config = config

            stdout = io.StringIO()
            stderr = io.StringIO()
            with patch("symphony_runtime.cli.build_runtime", return_value=runtime):
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = cli.main(["human-gate", "list"])

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                stdout.getvalue(),
                "RUN\tISSUE\tBRANCH\tCOMMIT\nlin-42\tLIN-42\tfeature/lin-42\tabc123\n",
            )
            self.assertEqual(stderr.getvalue(), "")

    def test_human_gate_list_warns_about_invalid_runs_without_hiding_valid_ones(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SymphonyConfig(
                workspace_root=Path(tmpdir),
                config_root=Path(tmpdir) / "config",
                runs_root=Path(tmpdir) / "runs",
                worktrees_root=Path(tmpdir) / "worktrees",
            )
            config.runs_root.mkdir(parents=True)

            valid_run = config.runs_root / "lin-42"
            valid_run.mkdir()
            (valid_run / "status.json").write_text(
                json.dumps(
                    {
                        "status": "human_gate",
                        "issue_id": "issue-id-123",
                        "issue_key": "LIN-42",
                        "branch": "feature/lin-42",
                        "commit_sha": "abc123",
                        "human_gate": {
                            "decision_required": True,
                            "decision_applied": False,
                        },
                    }
                )
            )

            invalid_run = config.runs_root / "lin-99"
            invalid_run.mkdir()
            (invalid_run / "status.json").write_text("{not json")

            runtime = Mock(spec=SymphonyRuntime)
            runtime.config = config

            stdout = io.StringIO()
            stderr = io.StringIO()
            with patch("symphony_runtime.cli.build_runtime", return_value=runtime):
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = cli.main(["human-gate", "list"])

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                stdout.getvalue(),
                "RUN\tISSUE\tBRANCH\tCOMMIT\nlin-42\tLIN-42\tfeature/lin-42\tabc123\n",
            )
            self.assertEqual(
                stderr.getvalue(),
                "WARNING: Skipped invalid Human Gate run lin-99: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)\n",
            )

    def test_human_gate_show_prints_resolved_run_details(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SymphonyConfig(
                workspace_root=Path(tmpdir),
                config_root=Path(tmpdir) / "config",
                runs_root=Path(tmpdir) / "runs",
                worktrees_root=Path(tmpdir) / "worktrees",
            )
            config.runs_root.mkdir(parents=True)

            resolved_run = config.runs_root / "lin-42"
            resolved_run.mkdir()
            (resolved_run / "status.json").write_text(
                json.dumps(
                    {
                        "status": "done",
                        "issue_id": "issue-id-123",
                        "issue_key": "LIN-42",
                        "branch": "feature/lin-42",
                        "commit_sha": "abc123",
                        "human_gate": {
                            "decision_required": True,
                            "decision_applied": True,
                            "decision": "approve",
                            "note": "Ship it",
                            "next_action": "ready_for_pr",
                            "applied_at": "2026-03-15T11:00:00Z",
                        },
                    }
                )
            )

            runtime = Mock(spec=SymphonyRuntime)
            runtime.config = config

            stdout = io.StringIO()
            stderr = io.StringIO()
            with patch("symphony_runtime.cli.build_runtime", return_value=runtime):
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = cli.main(["human-gate", "show", "--run", "lin-42"])

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                stdout.getvalue(),
                "RUN: lin-42\nISSUE: LIN-42\nBRANCH: feature/lin-42\nCOMMIT: abc123\nDECISION: approve\nNOTE: Ship it\nNEXT_ACTION: ready_for_pr\n",
            )
            self.assertEqual(stderr.getvalue(), "")

    def test_ready_for_pr_list_prints_approved_runs(self):
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
                            "decision_required": True,
                            "decision_applied": True,
                            "decision": "approve",
                            "note": "Ship it",
                            "next_action": "ready_for_pr",
                            "applied_at": "2026-03-15T11:00:00Z",
                        },
                    }
                )
            )

            not_ready_run = config.runs_root / "lin-43"
            not_ready_run.mkdir()
            (not_ready_run / "status.json").write_text(
                json.dumps(
                    {
                        "status": "done",
                        "issue_id": "issue-id-456",
                        "issue_key": "LIN-43",
                        "branch": "feature/lin-43",
                        "commit_sha": "def456",
                        "human_gate": {
                            "decision_required": True,
                            "decision_applied": True,
                            "decision": "reject",
                            "note": "Needs work",
                            "next_action": "close_out",
                            "applied_at": "2026-03-15T11:05:00Z",
                        },
                    }
                )
            )

            runtime = Mock(spec=SymphonyRuntime)
            runtime.config = config

            stdout = io.StringIO()
            stderr = io.StringIO()
            with patch("symphony_runtime.cli.build_runtime", return_value=runtime):
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = cli.main(["ready-for-pr", "list"])

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                stdout.getvalue(),
                "RUN\tISSUE\tBRANCH\tCOMMIT\nlin-42\tLIN-42\tfeature/lin-42\tabc123\n",
            )
            self.assertEqual(stderr.getvalue(), "")

    def test_ready_for_pr_list_warns_about_invalid_runs_without_hiding_valid_ones(self):
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
                            "decision_required": False,
                            "decision_applied": True,
                            "decision": "approve",
                            "note": "Ship it",
                            "next_action": "ready_for_pr",
                            "applied_at": "2026-03-15T11:00:00Z",
                        },
                    }
                )
            )

            invalid_run = config.runs_root / "lin-99"
            invalid_run.mkdir()
            (invalid_run / "status.json").write_text("{not json")

            runtime = Mock(spec=SymphonyRuntime)
            runtime.config = config

            stdout = io.StringIO()
            stderr = io.StringIO()
            with patch("symphony_runtime.cli.build_runtime", return_value=runtime):
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = cli.main(["ready-for-pr", "list"])

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                stdout.getvalue(),
                "RUN\tISSUE\tBRANCH\tCOMMIT\nlin-42\tLIN-42\tfeature/lin-42\tabc123\n",
            )
            self.assertEqual(
                stderr.getvalue(),
                "WARNING: Skipped invalid ready-for-pr run lin-99: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)\n",
            )

    @patch("symphony_runtime.cli.build_runtime")
    def test_ready_for_pr_create_delegates_to_runtime_and_prints_url(self, build_runtime):
        runtime = Mock(spec=SymphonyRuntime)
        runtime.create_pr_from_run.return_value = "https://github.com/o/r/pull/42"
        build_runtime.return_value = runtime

        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = cli.main(["ready-for-pr", "create", "--run", "lin-42"])

        self.assertEqual(exit_code, 0)
        runtime.create_pr_from_run.assert_called_once_with("lin-42")
        self.assertEqual(stdout.getvalue(), "https://github.com/o/r/pull/42\n")
        self.assertEqual(stderr.getvalue(), "")

    @patch("symphony_runtime.cli.build_runtime")
    def test_pr_opened_refresh_reviews_delegates_to_runtime_and_prints_confirmation(self, build_runtime):
        runtime = Mock(spec=SymphonyRuntime)
        build_runtime.return_value = runtime

        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = cli.main(["pr-opened", "refresh-reviews", "--run", "lin-42"])

        self.assertEqual(exit_code, 0)
        runtime.refresh_pr_reviews_from_run.assert_called_once_with("lin-42")
        self.assertEqual(stdout.getvalue(), "Refreshed PR reviews for lin-42\n")
        self.assertEqual(stderr.getvalue(), "")

    @patch("symphony_runtime.cli.build_runtime")
    def test_pr_opened_show_reviews_delegates_to_runtime_and_prints_summary(self, build_runtime):
        runtime = Mock(spec=SymphonyRuntime)
        runtime.get_pr_review_status_from_run.return_value = {
            "run_ref": "lin-42",
            "blocking_review_count": 1,
            "unresolved_findings_count": 2,
            "review_triage_path": "/tmp/run/pr_review_triage.md",
            "review_findings_path": "/tmp/run/pr_review_findings.json",
        }
        build_runtime.return_value = runtime

        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = cli.main(["pr-opened", "show-reviews", "--run", "lin-42"])

        self.assertEqual(exit_code, 0)
        runtime.get_pr_review_status_from_run.assert_called_once_with("lin-42")
        self.assertEqual(
            stdout.getvalue(),
            "RUN: lin-42\n"
            "BLOCKING_REVIEWS: 1\n"
            "UNRESOLVED_FINDINGS: 2\n"
            "TRIAGE: /tmp/run/pr_review_triage.md\n"
            "FINDINGS: /tmp/run/pr_review_findings.json\n",
        )
        self.assertEqual(stderr.getvalue(), "")

    @patch("symphony_runtime.cli.build_runtime")
    def test_pr_opened_show_review_diff_delegates_to_runtime_and_prints_diff_summary(self, build_runtime):
        runtime = Mock(spec=SymphonyRuntime)
        runtime.get_pr_review_status_from_run.return_value = {
            "run_ref": "lin-42",
            "blocking_review_count": 1,
            "unresolved_findings_count": 2,
            "newly_introduced_findings_count": 1,
            "resolved_findings_count": 1,
            "review_diff_path": "/tmp/run/pr_review_diff.json",
        }
        build_runtime.return_value = runtime

        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = cli.main(["pr-opened", "show-review-diff", "--run", "lin-42"])

        self.assertEqual(exit_code, 0)
        runtime.get_pr_review_status_from_run.assert_called_once_with("lin-42")
        self.assertEqual(
            stdout.getvalue(),
            "RUN: lin-42\n"
            "BLOCKING_REVIEWS: 1\n"
            "UNRESOLVED_FINDINGS: 2\n"
            "NEW_FINDINGS: 1\n"
            "RESOLVED_FINDINGS: 1\n"
            "DIFF: /tmp/run/pr_review_diff.json\n",
        )
        self.assertEqual(stderr.getvalue(), "")

    @patch("symphony_runtime.cli.build_runtime")
    def test_pr_opened_acknowledge_reviews_requires_explicit_state_and_delegates_to_runtime(self, build_runtime):
        runtime = Mock(spec=SymphonyRuntime)
        build_runtime.return_value = runtime

        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = cli.main([
                "pr-opened",
                "acknowledge-reviews",
                "--run",
                "lin-42",
                "--state",
                "addressed",
                "--note",
                "Handled locally",
            ])

        self.assertEqual(exit_code, 0)
        runtime.acknowledge_pr_reviews_from_run.assert_called_once_with("lin-42", "addressed", "Handled locally")
        self.assertEqual(stdout.getvalue(), "Acknowledged PR reviews for lin-42 as addressed\n")
        self.assertEqual(stderr.getvalue(), "")

    @patch("symphony_runtime.cli.build_runtime")
    def test_pr_opened_acknowledge_reviews_rejects_note_without_state(self, build_runtime):
        runtime = Mock(spec=SymphonyRuntime)
        build_runtime.return_value = runtime

        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as exc:
                cli.main([
                    "pr-opened",
                    "acknowledge-reviews",
                    "--run",
                    "lin-42",
                    "--note",
                    "Handled locally",
                ])

        self.assertEqual(exc.exception.code, 2)
        runtime.acknowledge_pr_reviews_from_run.assert_not_called()
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("--state", stderr.getvalue())

    @patch("symphony_runtime.cli.build_runtime")
    def test_human_gate_show_package_prints_decision_package_summary(self, build_runtime):
        runtime = Mock(spec=SymphonyRuntime)
        runtime.get_human_gate_package_from_run.return_value = {
            "run_ref": "lin-42",
            "issue_key": "LIN-42",
            "branch": "feature/lin-42",
            "recommendation": "review",
            "verification_path": "/tmp/run/verification.md",
            "review_path": "/tmp/run/review.md",
            "blocking_review_count": 1,
            "unresolved_findings_count": 2,
            "acknowledgement_state": "addressed",
            "package_markdown_path": "/tmp/run/human_gate_package.md",
        }
        build_runtime.return_value = runtime

        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = cli.main(["human-gate", "show-package", "--run", "lin-42"])

        self.assertEqual(exit_code, 0)
        runtime.get_human_gate_package_from_run.assert_called_once_with("lin-42")
        self.assertEqual(
            stdout.getvalue(),
            "RUN: lin-42\n"
            "ISSUE: LIN-42\n"
            "BRANCH: feature/lin-42\n"
            "RECOMMENDATION: review\n"
            "VERIFICATION: /tmp/run/verification.md\n"
            "REVIEW: /tmp/run/review.md\n"
            "BLOCKING_REVIEWS: 1\n"
            "UNRESOLVED_FINDINGS: 2\n"
            "ACKNOWLEDGEMENT: addressed\n"
            "PACKAGE: /tmp/run/human_gate_package.md\n",
        )
        self.assertEqual(stderr.getvalue(), "")

    @patch("symphony_runtime.cli.build_runtime")
    def test_pr_opened_prepare_merge_delegates_to_runtime_and_prints_short_result(self, build_runtime):
        runtime = Mock(spec=SymphonyRuntime)
        runtime.prepare_merge_from_run.return_value = {
            "run_ref": "lin-42",
            "merge_preparation_path": "/tmp/run/merge_preparation.md",
        }
        build_runtime.return_value = runtime

        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = cli.main(["pr-opened", "prepare-merge", "--run", "lin-42"])

        self.assertEqual(exit_code, 0)
        runtime.prepare_merge_from_run.assert_called_once_with("lin-42")
        self.assertEqual(
            stdout.getvalue(),
            "RUN: lin-42\nMERGE_PREPARATION: /tmp/run/merge_preparation.md\n",
        )
        self.assertEqual(stderr.getvalue(), "")
