import json
import tempfile
import unittest
from pathlib import Path

from symphony_runtime.config import SymphonyConfig
from symphony_runtime.daemon import SymphonyRuntime


class RuntimeHumanGatePreviewTests(unittest.TestCase):
    def test_write_human_gate_preview_persists_comment_text(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = SymphonyRuntime(
                config=SymphonyConfig(
                    workspace_root=Path(tmpdir),
                    config_root=Path(tmpdir) / "config",
                    runs_root=Path(tmpdir) / "runs",
                    worktrees_root=Path(tmpdir) / "worktrees",
                )
            )
            run_root = Path(tmpdir) / "runs" / "SYM-LIN-42"
            run_root.mkdir(parents=True)

            preview = runtime.write_human_gate_preview(
                run_root=run_root,
                issue_key="LIN-42",
                branch="sym/LIN-42-fix-output",
                commit_sha="dry-run",
                recommendation="ready",
                summary="Dry-run package prepared",
                verification="Preflight passed",
                review="Review not run in dry mode",
            )

            self.assertEqual(
                preview,
                "\n".join(
                    [
                        "Human Gate for LIN-42",
                        "Recommendation: ready",
                        "Branch: sym/LIN-42-fix-output",
                        "Commit: dry-run",
                        "",
                        "Summary:",
                        "Dry-run package prepared",
                        "",
                        "Verification:",
                        "Preflight passed",
                        "",
                        "Review:",
                        "Review not run in dry mode",
                    ]
                ),
            )
            self.assertEqual((run_root / "human_gate.md").read_text(), preview)

            status_payload = json.loads((run_root / "status.json").read_text())
            self.assertEqual(status_payload["human_gate"]["preview_path"], "human_gate.md")
            self.assertNotIn("summary_path", status_payload)
            self.assertNotIn("verification_path", status_payload)
            self.assertNotIn("review_path", status_payload)

            state_payload = json.loads((run_root / "state.json").read_text())
            self.assertEqual(state_payload["human_gate"]["preview_path"], "human_gate.md")
            self.assertNotIn("summary_path", state_payload)
            self.assertNotIn("verification_path", state_payload)
            self.assertNotIn("review_path", state_payload)
