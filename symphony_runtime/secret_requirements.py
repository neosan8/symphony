from __future__ import annotations

import os


def _validate_required_secrets(required_secrets: object) -> list[str]:
    if required_secrets is None:
        return []
    if not isinstance(required_secrets, list):
        raise ValueError("repo_contract.required_secrets must be a list of non-empty secret names")
    if any(not isinstance(secret, str) or not secret.strip() for secret in required_secrets):
        raise ValueError("repo_contract.required_secrets must be a list of non-empty secret names")
    return required_secrets


def check_required_secrets(repo_contract: dict) -> tuple[bool, list[str]]:
    required = _validate_required_secrets(repo_contract.get("required_secrets"))
    missing = sorted(secret for secret in required if not os.environ.get(secret, "").strip())
    return (len(missing) == 0, missing)
