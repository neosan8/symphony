import json
import tempfile
import unittest
from pathlib import Path

from symphony_runtime.models import RunStatus
from symphony_runtime.run_store import initialize_run_state


class RunBootstrapTests(unittest.TestCase):
    def test_initialize_run_state_creates_state_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir) / "SYM-001"
            state = initialize_run_state(run_root, "LIN-42", "symphony")
            self.assertEqual(state["issue_key"], "LIN-42")
            self.assertTrue((run_root / "state.json").exists())
            written = json.loads((run_root / "state.json").read_text())
            self.assertEqual(written["status"], RunStatus.TODO.value)

    def test_initialize_run_state_returns_existing_state_without_overwriting_it(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir) / "SYM-001"
            run_root.mkdir(parents=True)
            existing_state = {
                "status": "in_progress",
                "phase": "execution",
                "issue_key": "LIN-42",
                "repo_key": "symphony",
                "started_at": "2026-03-14T00:00:00+00:00",
                "updated_at": "2026-03-14T00:05:00+00:00",
            }
            state_path = run_root / "state.json"
            state_path.write_text(json.dumps(existing_state, indent=2))

            state = initialize_run_state(run_root, "LIN-99", "different-repo")

            self.assertEqual(state, existing_state)
            written = json.loads(state_path.read_text())
            self.assertEqual(written, existing_state)


if __name__ == "__main__":
    unittest.main()
