import unittest

from symphony_runtime.config import SymphonyConfig
from symphony_runtime.models import RunStatus


class RuntimeBootstrapTests(unittest.TestCase):
    def test_default_config_uses_workspace_paths(self):
        config = SymphonyConfig.default()
        self.assertTrue(str(config.config_root).endswith("config/symphony"))
        self.assertTrue(str(config.runs_root).endswith("symphony-runs"))
        self.assertTrue(str(config.worktrees_root).endswith("worktrees"))

    def test_run_status_contains_human_gate(self):
        self.assertEqual(RunStatus.HUMAN_GATE.value, "human_gate")


if __name__ == "__main__":
    unittest.main()
