import tempfile
import unittest
from pathlib import Path

from symphony_runtime.config import SymphonyConfig
from symphony_runtime.daemon import SymphonyRuntime


class MilestoneOneFlowTests(unittest.TestCase):
    def test_runtime_bootstraps_single_issue_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir)
            config = SymphonyConfig(
                workspace_root=workspace_root,
                config_root=workspace_root / "config",
                runs_root=workspace_root / "runs",
                worktrees_root=workspace_root / "worktrees",
            )
            runtime = SymphonyRuntime(config=config)
            self.assertEqual(runtime.config.max_concurrency, 2)

    def test_runtime_ensures_workspace_roots_exist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir)
            config = SymphonyConfig(
                workspace_root=workspace_root,
                config_root=workspace_root / "config",
                runs_root=workspace_root / "runs",
                worktrees_root=workspace_root / "worktrees",
            )
            runtime = SymphonyRuntime(config=config)

            runtime.ensure_workspace_roots()

            self.assertTrue(config.config_root.exists())
            self.assertTrue(config.runs_root.exists())
            self.assertTrue(config.worktrees_root.exists())


if __name__ == "__main__":
    unittest.main()
