import unittest
from dataclasses import FrozenInstanceError

from symphony_runtime.verification import VerificationResult


class VerificationResultTests(unittest.TestCase):
    def test_commands_are_stored_as_immutable_tuple(self):
        result = VerificationResult(
            commands=("python -m pytest", "ruff check ."),
            passed=True,
            notes="all good",
        )

        self.assertEqual(result.commands, ("python -m pytest", "ruff check ."))
        self.assertIsInstance(result.commands, tuple)

    def test_frozen_dataclass_blocks_reassignment(self):
        result = VerificationResult(
            commands=("python -m pytest",),
            passed=True,
            notes="all good",
        )

        with self.assertRaises(FrozenInstanceError):
            result.commands = ("ruff check .",)
