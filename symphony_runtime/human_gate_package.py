import json
from pathlib import Path
from typing import Any


REQUIRED_ARTIFACT_KEYS = (
    "summary_path",
    "verification_path",
    "review_path",
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _required_string(payload: dict[str, Any], key: str, source: Path) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"Missing or invalid {key} in {source}")
    return value


def _optional_string(payload: dict[str, Any], key: str) -> str | None:
    value = str(payload.get(key) or "").strip()
    return value or None


def _require_matching_required_artifact_path(status_payload: dict[str, Any], state_payload: dict[str, Any], key: str, status_path: Path, state_path: Path) -> str:
    status_value = _required_string(status_payload, key, status_path)
    state_value = _required_string(state_payload, key, state_path)
    if status_value != state_value:
        raise ValueError(f"Required artifact metadata mismatch between {status_path} and {state_path}: {key}")
    return status_value


def _validate_run_relative_path(path_value: str, source: Path, key: str, *, error_prefix: str) -> Path:
    artifact_path = Path(path_value)
    if artifact_path.is_absolute() or not artifact_path.parts:
        raise ValueError(f"Invalid {key} in {source}: {path_value}")
    resolved_path = (source.parent / artifact_path).resolve()
    try:
        resolved_path.relative_to(source.parent.resolve())
    except ValueError as exc:
        raise ValueError(f"Invalid {key} in {source}: {path_value}") from exc
    if not resolved_path.exists():
        raise ValueError(f"{error_prefix} {source}: {path_value}")
    return artifact_path


def _require_matching_review_path(status_pr_payload: dict[str, Any], state_payload: dict[str, Any], key: str, status_path: Path, state_path: Path) -> str | None:
    status_value = _optional_string(status_pr_payload, key)
    state_pr_payload = state_payload.get("pr")
    state_value = _optional_string(state_pr_payload, key) if isinstance(state_pr_payload, dict) else None
    if status_value is None and state_value is None:
        return None
    if status_value is None or state_value is None:
        raise ValueError(f"Run is not in a review-snapshotted state; missing PR review metadata in {status_path}: {key}")
    if status_value != state_value:
        raise ValueError(f"PR review metadata mismatch between {status_path} and {state_path}: {key}")
    return status_value


def build_human_gate_package(run_root: Path) -> dict[str, Any]:
    status_path = run_root / "status.json"
    state_path = run_root / "state.json"
    status_payload = _load_json(status_path)
    state_payload = _load_json(state_path)

    package: dict[str, Any] = {
        "run_root": str(run_root),
        "status": _required_string(status_payload, "status", status_path),
        "issue_key": _required_string(status_payload, "issue_key", status_path),
    }

    for key in REQUIRED_ARTIFACT_KEYS:
        path_value = _require_matching_required_artifact_path(
            status_payload,
            state_payload,
            key,
            status_path,
            state_path,
        )
        _validate_run_relative_path(
            path_value,
            status_path,
            key,
            error_prefix="Missing required artifact referenced by",
        )
        package[key] = path_value

    branch = _optional_string(status_payload, "branch")
    if branch:
        package["branch"] = branch

    commit_sha = _optional_string(status_payload, "commit_sha")
    if commit_sha:
        package["commit_sha"] = commit_sha

    human_gate = status_payload.get("human_gate")
    if not isinstance(human_gate, dict):
        raise ValueError(f"Missing or invalid human_gate in {status_path}")

    package["recommendation"] = _required_string(human_gate, "recommendation", status_path)
    package["decision_required"] = bool(human_gate.get("decision_required"))
    package["decision_applied"] = bool(human_gate.get("decision_applied"))

    for key in ("decision", "note", "next_action", "applied_at"):
        value = _optional_string(human_gate, key)
        if value is not None:
            package[key] = value

    pr_payload = status_payload.get("pr")
    if isinstance(pr_payload, dict):
        pr_url = _optional_string(pr_payload, "url")
        if pr_url is not None:
            package["pr_url"] = pr_url

        review_findings_path = _require_matching_review_path(
            pr_payload,
            state_payload,
            "review_findings_path",
            status_path,
            state_path,
        )
        if review_findings_path is not None:
            package["review_findings_path"] = review_findings_path
            findings_path = _validate_run_relative_path(
                review_findings_path,
                status_path,
                "review_findings_path",
                error_prefix="Missing PR review artifact referenced by",
            )
            findings_payload = _load_json(run_root / findings_path)
            unresolved_findings = findings_payload.get("unresolved_findings") or []
            if not isinstance(unresolved_findings, list):
                raise ValueError("unresolved_findings must be a list")
            package["unresolved_findings_count"] = len(unresolved_findings)
            blocking_count = findings_payload.get("blocking_count")
            if isinstance(blocking_count, int):
                package["blocking_review_count"] = blocking_count

        review_diff_path = _require_matching_review_path(
            pr_payload,
            state_payload,
            "review_diff_path",
            status_path,
            state_path,
        )
        if review_diff_path is not None:
            package["review_diff_path"] = review_diff_path
            diff_path = _validate_run_relative_path(
                review_diff_path,
                status_path,
                "review_diff_path",
                error_prefix="Missing PR review artifact referenced by",
            )
            diff_payload = _load_json(run_root / diff_path)
            for source_key, package_key in (
                ("newly_introduced_count", "newly_introduced_findings_count"),
                ("resolved_count", "resolved_findings_count"),
            ):
                value = diff_payload.get(source_key)
                if isinstance(value, int):
                    package[package_key] = value

        for key in (
            "blocking_review_count",
            "newly_introduced_findings_count",
            "resolved_findings_count",
        ):
            value = pr_payload.get(key)
            if isinstance(value, int):
                package[key] = value

        acknowledgement = pr_payload.get("review_acknowledgement")
        if isinstance(acknowledgement, dict):
            acknowledgement_state = _optional_string(acknowledgement, "state")
            acknowledgement_path = _optional_string(acknowledgement, "path")
            if acknowledgement_state is not None:
                package["acknowledgement_state"] = acknowledgement_state
            if acknowledgement_path is not None:
                _validate_run_relative_path(
                    acknowledgement_path,
                    status_path,
                    "review_acknowledgement.path",
                    error_prefix="Missing PR review artifact referenced by",
                )
                package["acknowledgement_path"] = acknowledgement_path

    return package


def render_human_gate_package_markdown(package: dict[str, Any]) -> str:
    lines = [
        "# Human Gate Decision Package",
        "",
        f"Issue: {package['issue_key']}",
        f"Status: {package['status']}",
        f"Summary: {package['summary_path']}",
        f"Verification: {package['verification_path']}",
        f"Review: {package['review_path']}",
        f"Recommendation: {package['recommendation']}",
    ]
    optional_lines = [
        ("Decision", package.get("decision")),
        ("Next Action", package.get("next_action")),
        ("Blocking Review Count", package.get("blocking_review_count")),
        ("Unresolved Findings Count", package.get("unresolved_findings_count")),
        ("Newly Introduced Findings Count", package.get("newly_introduced_findings_count")),
        ("Resolved Findings Count", package.get("resolved_findings_count")),
        ("Acknowledgement State", package.get("acknowledgement_state")),
        ("Acknowledgement Path", package.get("acknowledgement_path")),
        ("Review Diff Path", package.get("review_diff_path")),
    ]
    for label, value in optional_lines:
        if value is not None:
            lines.append(f"{label}: {value}")
    return "\n".join(lines) + "\n"
