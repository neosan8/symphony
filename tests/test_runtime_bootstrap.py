import os
import unittest
from pathlib import Path
from unittest.mock import patch

from symphony_runtime.config import SymphonyConfig
from symphony_runtime.models import RunStatus


class RuntimeBootstrapTests(unittest.TestCase):
    def test_default_config_uses_workspace_paths(self):
        with patch.dict(os.environ, {}, clear=False), patch("symphony_runtime.config.Path.home", return_value=Path("/tmp/test-home")):
            config = SymphonyConfig.default()

        self.assertEqual(config.workspace_root, Path("/tmp/test-home/.openclaw/workspace"))
        self.assertEqual(config.config_root, Path("/tmp/test-home/.openclaw/workspace/config/symphony"))
        self.assertEqual(config.runs_root, Path("/tmp/test-home/.openclaw/workspace/symphony-runs"))
        self.assertEqual(config.worktrees_root, Path("/tmp/test-home/.openclaw/workspace/worktrees"))

    def test_default_config_uses_env_override_when_present(self):
        with patch.dict(os.environ, {"SYMPHONY_WORKSPACE_ROOT": "/tmp/custom-symphony"}, clear=False), patch(
            "symphony_runtime.config.Path.home", return_value=Path("/tmp/ignored-home")
        ):
            config = SymphonyConfig.default()

        self.assertEqual(config.workspace_root, Path("/tmp/custom-symphony"))
        self.assertEqual(config.config_root, Path("/tmp/custom-symphony/config/symphony"))
        self.assertEqual(config.runs_root, Path("/tmp/custom-symphony/symphony-runs"))
        self.assertEqual(config.worktrees_root, Path("/tmp/custom-symphony/worktrees"))

    def test_run_status_contains_human_gate(self):
        self.assertEqual(RunStatus.HUMAN_GATE.value, "human_gate")


if __name__ == "__main__":
    unittest.main()
