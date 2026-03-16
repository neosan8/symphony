import tempfile
import unittest
from pathlib import Path

from symphony_runtime.preflight import run_preflight


class PreflightTests(unittest.TestCase):
    def test_preflight_succeeds_when_requirements_are_met(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            result = run_preflight(
                repo_root=repo_root,
                repo_contract={"boot": "python -m symphony_runtime", "test": "pytest"},
                context_ready=True,
                secrets_ready=True,
            )
            self.assertTrue(result.ok)
            self.assertEqual(result.reason, "")

    def test_preflight_blocks_when_context_is_not_ready(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            result = run_preflight(
                repo_root=repo_root,
                repo_contract={"boot": "python -m symphony_runtime", "test": "pytest"},
                context_ready=False,
                secrets_ready=True,
            )
            self.assertFalse(result.ok)
            self.assertEqual(result.reason, "context packet is incomplete")

    def test_preflight_blocks_when_secrets_are_not_ready(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            result = run_preflight(
                repo_root=repo_root,
                repo_contract={"boot": "python -m symphony_runtime", "test": "pytest"},
                context_ready=True,
                secrets_ready=False,
            )
            self.assertFalse(result.ok)
            self.assertEqual(result.reason, "required secrets are unavailable")

    def test_preflight_reports_missing_secret_names(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            result = run_preflight(
                repo_root=repo_root,
                repo_contract={"boot": "python", "test": "pytest"},
                context_ready=True,
                secrets_ready=False,
                missing_secrets=["SENTRY_AUTH_TOKEN"],
            )
            self.assertEqual(result.reason, "required secrets are unavailable: SENTRY_AUTH_TOKEN")

    def test_preflight_blocks_without_boot_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            result = run_preflight(
                repo_root=repo_root,
                repo_contract={"test": "pytest"},
                context_ready=True,
                secrets_ready=True,
            )
            self.assertFalse(result.ok)
            self.assertIn("boot", result.reason)

    def test_preflight_blocks_without_test_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            result = run_preflight(
                repo_root=repo_root,
                repo_contract={"boot": "python -m symphony_runtime"},
                context_ready=True,
                secrets_ready=True,
            )
            self.assertFalse(result.ok)
            self.assertEqual(result.reason, "test command missing from repo contract")
