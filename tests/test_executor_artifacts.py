import json
import tempfile
import unittest
from pathlib import Path

from symphony_runtime.run_store import initialize_run_state, write_summary_artifacts


class ExecutorArtifactTests(unittest.TestCase):
    def test_write_summary_artifacts_creates_summary_and_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir)
            write_summary_artifacts(
                run_root,
                summary="# Summary\nDone.",
                verification="# Verification\nPending.",
                review="# Review\nPending.",
                status_payload={"status": "in_progress"},
            )
            self.assertTrue((run_root / "summary.md").exists())
            self.assertTrue((run_root / "verification.md").exists())
            self.assertTrue((run_root / "review.md").exists())
            self.assertEqual((run_root / "summary.md").read_text(), "# Summary\nDone.")
            self.assertEqual((run_root / "verification.md").read_text(), "# Verification\nPending.")
            self.assertEqual((run_root / "review.md").read_text(), "# Review\nPending.")
            payload = json.loads((run_root / "status.json").read_text())
            self.assertEqual(payload["status"], "in_progress")

    def test_write_summary_artifacts_updates_existing_run_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir)
            initialize_run_state(run_root, issue_key="LIN-42", repo_key="symphony")

            write_summary_artifacts(
                run_root,
                summary="Execution failed for Fix output",
                verification="Codex execution exited with code 7.",
                review="Review logs.",
                status_payload={
                    "status": "human_gate",
                    "branch": "feature/lin-42",
                    "return_code": 7,
                    "stdout_path": "/tmp/stdout.log",
                    "stderr_path": "/tmp/stderr.log",
                },
            )

            state = json.loads((run_root / "state.json").read_text())
            status = json.loads((run_root / "status.json").read_text())
            self.assertEqual(state["issue_key"], "LIN-42")
            self.assertEqual(state["repo_key"], "symphony")
            self.assertEqual(state["status"], "human_gate")
            self.assertEqual(state["branch"], "feature/lin-42")
            self.assertEqual(state["return_code"], 7)
            self.assertEqual(state["stdout_path"], "/tmp/stdout.log")
            self.assertEqual(state["stderr_path"], "/tmp/stderr.log")
            self.assertEqual(status["return_code"], state["return_code"])
            self.assertIn("updated_at", state)


if __name__ == "__main__":
    unittest.main()
