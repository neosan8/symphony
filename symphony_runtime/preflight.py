from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    reason: str = ""


def run_preflight(
    repo_root: Path,
    repo_contract: dict,
    context_ready: bool,
    secrets_ready: bool,
    missing_secrets: list[str] | None = None,
) -> PreflightResult:
    if not context_ready:
        return PreflightResult(False, "context packet is incomplete")
    if not secrets_ready:
        detail = f": {', '.join(missing_secrets)}" if missing_secrets else ""
        return PreflightResult(False, f"required secrets are unavailable{detail}")
    if not repo_contract.get("boot"):
        return PreflightResult(False, "boot command missing from repo contract")
    if not repo_contract.get("test"):
        return PreflightResult(False, "test command missing from repo contract")
    return PreflightResult(True, "")
