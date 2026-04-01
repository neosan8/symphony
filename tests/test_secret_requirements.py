import os
import unittest
from unittest.mock import patch

from symphony_runtime.secret_requirements import check_required_secrets


class SecretRequirementTests(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_check_required_secrets_defaults_to_ready_when_not_declared(self):
        ok, missing = check_required_secrets({})
        self.assertTrue(ok)
        self.assertEqual(missing, [])

    @patch.dict(os.environ, {"OPENAI_API_KEY": "x", "SENTRY_AUTH_TOKEN": "y"}, clear=True)
    def test_check_required_secrets_is_ready_when_all_required_env_vars_exist(self):
        ok, missing = check_required_secrets({"required_secrets": ["OPENAI_API_KEY", "SENTRY_AUTH_TOKEN"]})
        self.assertTrue(ok)
        self.assertEqual(missing, [])

    @patch.dict(os.environ, {"OPENAI_API_KEY": "x"}, clear=True)
    def test_check_required_secrets_reports_missing_env_vars(self):
        ok, missing = check_required_secrets({"required_secrets": ["OPENAI_API_KEY", "SENTRY_AUTH_TOKEN"]})
        self.assertFalse(ok)
        self.assertEqual(missing, ["SENTRY_AUTH_TOKEN"])

    def test_check_required_secrets_rejects_malformed_required_secrets(self):
        with self.assertRaisesRegex(ValueError, "required_secrets"):
            check_required_secrets({"required_secrets": "OPENAI_API_KEY"})
