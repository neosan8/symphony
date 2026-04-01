from dataclasses import dataclass


@dataclass(frozen=True)
class VerificationResult:
    commands: tuple[str, ...]
    passed: bool
    notes: str
