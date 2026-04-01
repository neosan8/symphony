import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from symphony_runtime.human_gate_package import build_human_gate_package, render_human_gate_package_markdown
from symphony_runtime.models import RunStatus
from symphony_runtime.review_triage import summarize_review_payload


_PR_REVIEW_COMPARISON_FIELDS = (
    "source",
    "finding_id",
    "author",
    "body",
    "is_blocking",
)

_VALID_REVIEW_ACKNOWLEDGEMENT_STATES = {
    "reviewed",
    "addressed",
    "needs-follow-up",
}

_REQUIRED_MERGE_PREPARATION_ARTIFACT_KEYS = (
    "summary_path",
    "verification_path",
    "review_path",
)


def initialize_run_state(run_root: Path, issue_key: str, repo_key: str) -> dict:
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "logs").mkdir(exist_ok=True)
    (run_root / "artifacts").mkdir(exist_ok=True)
    state_path = run_root / "state.json"
    if state_path.exists():
        return json.loads(state_path.read_text())

    now = datetime.now(timezone.utc).isoformat()
    state = {
        "status": RunStatus.TODO.value,
        "phase": "preflight",
        "issue_key": issue_key,
        "repo_key": repo_key,
        "started_at": now,
        "updated_at": now,
    }
    state_path.write_text(json.dumps(state, indent=2))
    return state


def write_summary_artifacts(
    run_root: Path,
    summary: str,
    verification: str,
    review: str,
    status_payload: dict,
) -> None:
    summary_path = "summary.md"
    verification_path = "verification.md"
    review_path = "review.md"
    (run_root / summary_path).write_text(summary)
    (run_root / verification_path).write_text(verification)
    (run_root / review_path).write_text(review)
    persisted_status_payload = dict(status_payload)
    persisted_status_payload.update({
        "summary_path": summary_path,
        "verification_path": verification_path,
        "review_path": review_path,
    })
    (run_root / "status.json").write_text(json.dumps(persisted_status_payload, indent=2))
    update_run_state(run_root, persisted_status_payload)


def update_run_state(run_root: Path, status_payload: dict) -> dict:
    state_path = run_root / "state.json"
    now = datetime.now(timezone.utc).isoformat()
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    state.update(status_payload)
    state["updated_at"] = now
    state_path.write_text(json.dumps(state, indent=2))
    return state


def write_human_gate_preview_state(
    run_root: Path,
    *,
    issue_key: str,
    branch: str,
    commit_sha: str,
    recommendation: str,
) -> None:
    run_root.mkdir(parents=True, exist_ok=True)
    status_path = run_root / "status.json"
    payload = json.loads(status_path.read_text()) if status_path.exists() else {}
    human_gate = dict(payload.get("human_gate") or {})
    human_gate.update({
        "recommendation": recommendation,
        "preview_path": "human_gate.md",
    })
    payload.update({
        "status": payload.get("status", RunStatus.HUMAN_GATE.value),
        "issue_key": issue_key,
        "branch": branch,
        "commit_sha": commit_sha,
        "human_gate": human_gate,
    })
    status_path.write_text(json.dumps(payload, indent=2))
    update_run_state(run_root, payload)


def write_human_gate_handoff(
    run_root: Path,
    *,
    issue_id: str,
    issue_key: str,
    branch: str,
    worktree_path: str,
    base_branch: str,
    commit_sha: str,
    recommendation: str,
) -> None:
    run_root.mkdir(parents=True, exist_ok=True)
    status_path = run_root / "status.json"
    payload = json.loads(status_path.read_text()) if status_path.exists() else {}
    if not payload:
        state_path = run_root / "state.json"
        persisted_state = json.loads(state_path.read_text()) if state_path.exists() else {}
        for artifact_path_key in ("summary_path", "verification_path", "review_path"):
            if artifact_path_key in persisted_state:
                payload[artifact_path_key] = persisted_state[artifact_path_key]
    payload.update({
        "status": RunStatus.HUMAN_GATE.value,
        "issue_id": issue_id,
        "issue_key": issue_key,
        "branch": branch,
        "worktree_path": worktree_path,
        "base_branch": base_branch,
        "commit_sha": commit_sha,
        "human_gate": {
            "recommendation": recommendation,
            "decision_required": True,
            "decision_applied": False,
        },
    })
    status_path.write_text(json.dumps(payload, indent=2))
    update_run_state(run_root, payload)
    _write_human_gate_package(run_root)



def write_pr_opened(run_root: Path, pr_url: str) -> None:
    run_root.mkdir(parents=True, exist_ok=True)
    normalized_pr_url = str(pr_url or "").strip()
    if not normalized_pr_url:
        raise ValueError("PR URL must be non-empty")

    opened_at = datetime.now(timezone.utc).isoformat()
    status_path = run_root / "status.json"
    payload = json.loads(status_path.read_text()) if status_path.exists() else {}
    human_gate = dict(payload.get("human_gate") or {})
    if human_gate.get("decision") != "approve" or human_gate.get("next_action") != "ready_for_pr":
        raise ValueError(
            "write_pr_opened requires approved Human Gate decision with next_action == ready_for_pr"
        )

    human_gate["next_action"] = "pr_opened"
    payload.update({
        "human_gate": human_gate,
        "pr": {
            "url": normalized_pr_url,
            "opened_at": opened_at,
        },
    })
    (run_root / "pr_opened.md").write_text(
        "# PR Opened\n\n"
        f"Issue: {payload.get('issue_key', '')}\n"
        f"Branch: {payload.get('branch', '')}\n"
        f"PR URL: {normalized_pr_url}\n"
        f"Opened At: {opened_at}\n"
        f"Next Action: pr_opened\n"
    )
    status_path.write_text(json.dumps(payload, indent=2))
    update_run_state(run_root, payload)
    _write_human_gate_package(run_root)


def write_pr_review_snapshot(run_root: Path, review_json: str) -> None:
    run_root.mkdir(parents=True, exist_ok=True)
    fetched_at = datetime.now(timezone.utc).isoformat()
    review_comments_path = "pr_review_comments.json"
    review_summary_path = "pr_review_summary.md"
    review_findings_path = "pr_review_findings.json"
    previous_review_findings_path = "pr_review_findings.previous.json"
    review_diff_path = "pr_review_diff.json"
    review_triage_path = "pr_review_triage.md"
    status_path = run_root / "status.json"
    payload = json.loads(status_path.read_text()) if status_path.exists() else {}
    human_gate = dict(payload.get("human_gate") or {})
    pr_payload = dict(payload.get("pr") or {})
    normalized_pr_url = str(pr_payload.get("url") or "").strip()
    if human_gate.get("next_action") != "pr_opened" or not normalized_pr_url:
        raise ValueError(
            "write_pr_review_snapshot requires an opened PR with non-empty URL and next_action == pr_opened"
        )

    (run_root / review_comments_path).write_text(review_json)

    triage_summary = summarize_review_payload(review_json)
    findings_payload = {
        "total_findings": triage_summary.total_findings,
        "blocking_count": triage_summary.blocking_count,
        "unresolved_findings": [asdict(finding) for finding in triage_summary.unresolved_findings],
    }

    previous_findings_payload = None
    current_findings_file = run_root / review_findings_path
    if current_findings_file.exists():
        previous_findings_payload = json.loads(current_findings_file.read_text())
        (run_root / previous_review_findings_path).write_text(json.dumps(previous_findings_payload, indent=2))

    diff_payload = {
        "previous_findings_path": previous_review_findings_path if previous_findings_payload is not None else None,
        "current_findings_path": review_findings_path,
        "newly_introduced_count": 0,
        "resolved_count": 0,
        "newly_introduced_findings": [],
        "resolved_findings": [],
    }
    if previous_findings_payload is not None:
        previous_findings = _normalize_unresolved_findings(previous_findings_payload)
        current_findings = _normalize_unresolved_findings(findings_payload)
        previous_keys = {_finding_key(finding) for finding in previous_findings}
        current_keys = {_finding_key(finding) for finding in current_findings}
        diff_payload["newly_introduced_findings"] = [
            finding for finding in current_findings if _finding_key(finding) not in previous_keys
        ]
        diff_payload["resolved_findings"] = [
            finding for finding in previous_findings if _finding_key(finding) not in current_keys
        ]
        diff_payload["newly_introduced_count"] = len(diff_payload["newly_introduced_findings"])
        diff_payload["resolved_count"] = len(diff_payload["resolved_findings"])

    pr_payload.update({
        "url": normalized_pr_url,
        "review_fetched_at": fetched_at,
        "review_comments_path": review_comments_path,
        "previous_review_findings_path": previous_review_findings_path if previous_findings_payload is not None else None,
        "review_findings_path": review_findings_path,
        "review_diff_path": review_diff_path,
        "review_triage_path": review_triage_path,
        "blocking_review_count": triage_summary.blocking_count,
        "newly_introduced_findings_count": diff_payload["newly_introduced_count"],
        "resolved_findings_count": diff_payload["resolved_count"],
    })
    payload["pr"] = pr_payload

    (run_root / review_summary_path).write_text(
        "# PR Review Summary\n\n"
        f"Issue: {payload.get('issue_key', '')}\n"
        f"PR URL: {pr_payload.get('url', '')}\n"
        f"Review Fetched At: {fetched_at}\n\n"
        "Review snapshot captured.\n"
    )
    current_findings_file.write_text(json.dumps(findings_payload, indent=2))
    (run_root / review_diff_path).write_text(json.dumps(diff_payload, indent=2))
    triage_lines = [
        "# PR Review Triage",
        "",
        f"Issue: {payload.get('issue_key', '')}",
        f"PR URL: {pr_payload.get('url', '')}",
        f"Review Fetched At: {fetched_at}",
        f"Blocking Reviews: {triage_summary.blocking_count}",
        f"Still Unresolved Findings: {len(findings_payload['unresolved_findings'])}",
        f"Newly Introduced Findings: {diff_payload['newly_introduced_count']}",
        f"Resolved Findings: {diff_payload['resolved_count']}",
        "",
    ]
    if triage_summary.unresolved_findings:
        _append_review_finding_section(
            triage_lines,
            "Still Unresolved Findings",
            findings_payload["unresolved_findings"],
        )
    if diff_payload["newly_introduced_findings"]:
        _append_review_finding_section(
            triage_lines,
            "Newly Introduced Findings",
            diff_payload["newly_introduced_findings"],
        )
    if diff_payload["resolved_findings"]:
        _append_review_finding_section(
            triage_lines,
            "Resolved Findings",
            diff_payload["resolved_findings"],
        )
    if not triage_summary.unresolved_findings:
        triage_lines.append("No unresolved findings.")
    (run_root / review_triage_path).write_text("\n".join(triage_lines).rstrip() + "\n")
    status_path.write_text(json.dumps(payload, indent=2))
    update_run_state(run_root, payload)
    _write_human_gate_package(run_root)


def _normalize_unresolved_findings(findings_payload: dict) -> list[dict]:
    unresolved_findings = findings_payload.get("unresolved_findings") or []
    if not isinstance(unresolved_findings, list):
        raise ValueError("write_pr_review_snapshot requires unresolved_findings list")
    normalized_findings = []
    for finding in unresolved_findings:
        if not isinstance(finding, dict):
            raise ValueError("write_pr_review_snapshot requires unresolved_findings entries to be objects")
        normalized_findings.append({field_name: finding.get(field_name) for field_name in _PR_REVIEW_COMPARISON_FIELDS})
    return normalized_findings


def _finding_key(finding: dict) -> tuple:
    return tuple(finding.get(field_name) for field_name in _PR_REVIEW_COMPARISON_FIELDS)


def _format_review_finding(finding: dict) -> str:
    source_label = finding.get("source") or "unknown"
    if finding.get("is_blocking"):
        source_label = f"{source_label}/blocking"
    author_label = finding.get("author") or "unknown"
    body = finding.get("body") or ""
    return f"- [{source_label}] {author_label}: {body}"


def _append_review_finding_section(lines: list[str], heading: str, findings: list[dict]) -> None:
    if not findings:
        return
    lines.append(f"## {heading}")
    lines.append("")
    for finding in findings:
        if not isinstance(finding, dict):
            raise ValueError("write_pr_review_acknowledgement requires unresolved_findings entries to be objects")
        lines.append(_format_review_finding(finding))
    lines.append("")


def write_pr_review_acknowledgement(run_root: Path, state: str, note: str) -> None:
    run_root.mkdir(parents=True, exist_ok=True)
    acknowledged_at = datetime.now(timezone.utc).isoformat()
    acknowledgement_path = "pr_review_acknowledgement.md"
    status_path = run_root / "status.json"
    payload = json.loads(status_path.read_text()) if status_path.exists() else {}
    human_gate = dict(payload.get("human_gate") or {})
    pr_payload = dict(payload.get("pr") or {})
    normalized_pr_url = str(pr_payload.get("url") or "").strip()
    if human_gate.get("next_action") != "pr_opened" or not normalized_pr_url:
        raise ValueError(
            "write_pr_review_acknowledgement requires an opened PR with non-empty URL and next_action == pr_opened"
        )

    normalized_state = str(state or "").strip()
    if normalized_state not in _VALID_REVIEW_ACKNOWLEDGEMENT_STATES:
        raise ValueError(
            "write_pr_review_acknowledgement requires state to be one of: "
            + ", ".join(sorted(_VALID_REVIEW_ACKNOWLEDGEMENT_STATES))
        )

    review_findings_path = str(pr_payload.get("review_findings_path") or "").strip()
    if not review_findings_path:
        raise ValueError("write_pr_review_acknowledgement requires review_findings_path metadata")

    findings_payload = json.loads((run_root / review_findings_path).read_text())
    unresolved_findings = findings_payload.get("unresolved_findings") or []
    blocking_count = findings_payload.get("blocking_count")
    if not isinstance(unresolved_findings, list):
        raise ValueError("write_pr_review_acknowledgement requires unresolved_findings list")
    if not isinstance(blocking_count, int) or blocking_count < 0:
        raise ValueError("write_pr_review_acknowledgement requires non-negative blocking_count")

    diff_payload = json.loads((run_root / str(pr_payload.get("review_diff_path") or "pr_review_diff.json")).read_text())
    newly_introduced_findings = diff_payload.get("newly_introduced_findings") or []
    resolved_findings = diff_payload.get("resolved_findings") or []

    normalized_note = str(note or "").strip()
    acknowledgement_lines = [
        "# PR Review Acknowledgement",
        f"Issue: {payload.get('issue_key', '')}",
        f"PR URL: {normalized_pr_url}",
        f"Acknowledged At: {acknowledged_at}",
        f"State: {normalized_state}",
        f"Note: {normalized_note}",
        f"Blocking Reviews: {blocking_count}",
        f"Still Unresolved Findings: {len(unresolved_findings)}",
        f"Newly Introduced Findings: {len(newly_introduced_findings)}",
        f"Resolved Findings: {len(resolved_findings)}",
    ]
    if unresolved_findings:
        acknowledgement_lines.append("## Still Unresolved Findings")
        for finding in unresolved_findings:
            if not isinstance(finding, dict):
                raise ValueError(
                    "write_pr_review_acknowledgement requires unresolved_findings entries to be objects"
                )
            acknowledgement_lines.append(_format_review_finding(finding))
    if newly_introduced_findings:
        acknowledgement_lines.append("## Newly Introduced Findings")
        for finding in newly_introduced_findings:
            if not isinstance(finding, dict):
                raise ValueError(
                    "write_pr_review_acknowledgement requires unresolved_findings entries to be objects"
                )
            acknowledgement_lines.append(_format_review_finding(finding))
    if resolved_findings:
        acknowledgement_lines.append("## Resolved Findings")
        for finding in resolved_findings:
            if not isinstance(finding, dict):
                raise ValueError(
                    "write_pr_review_acknowledgement requires unresolved_findings entries to be objects"
                )
            acknowledgement_lines.append(_format_review_finding(finding))
    if not unresolved_findings:
        acknowledgement_lines.append("No unresolved findings.")
    (run_root / acknowledgement_path).write_text("\n".join(acknowledgement_lines).rstrip() + "\n")

    pr_payload["review_acknowledgement"] = {
        "acknowledged_at": acknowledged_at,
        "path": acknowledgement_path,
        "state": normalized_state,
        "note": normalized_note,
        "has_note": bool(normalized_note),
    }
    payload["pr"] = pr_payload
    status_path.write_text(json.dumps(payload, indent=2))
    update_run_state(run_root, payload)
    _write_human_gate_package(run_root)


def write_merge_preparation_artifacts(run_root: Path, merge_preparation: dict) -> None:
    run_root.mkdir(parents=True, exist_ok=True)
    merge_json_path = "merge_preparation.json"
    merge_markdown_path = "merge_preparation.md"

    (run_root / merge_json_path).write_text(json.dumps(merge_preparation, indent=2))
    markdown_lines = [
        "# Merge Preparation",
        "",
        f"Run: {merge_preparation['run_ref']}",
        f"Issue: {merge_preparation['issue_key']}",
        f"Branch: {merge_preparation['branch']}",
        f"Commit: {merge_preparation['commit_sha']}",
        f"PR URL: {merge_preparation['pr_url']}",
        f"Blocking Review Count: {merge_preparation['blocking_review_count']}",
        f"Acknowledgement State: {merge_preparation['acknowledgement_state']}",
        f"Summary: {merge_preparation['summary_path']}",
        f"Verification: {merge_preparation['verification_path']}",
        f"Review: {merge_preparation['review_path']}",
        f"Human Gate Package: {merge_preparation['human_gate_package_path']}",
        f"Human Gate Package JSON: {merge_preparation['human_gate_package_json_path']}",
    ]
    (run_root / merge_markdown_path).write_text("\n".join(markdown_lines) + "\n")

    status_path = run_root / "status.json"
    payload = json.loads(status_path.read_text()) if status_path.exists() else {}
    pr_payload = dict(payload.get("pr") or {})
    pr_payload["merge_preparation"] = {
        "json_path": merge_json_path,
        "markdown_path": merge_markdown_path,
        "human_gate_package_path": merge_preparation["human_gate_package_path"],
        "human_gate_package_json_path": merge_preparation["human_gate_package_json_path"],
        "acknowledgement_state": merge_preparation["acknowledgement_state"],
        "blocking_review_count": merge_preparation["blocking_review_count"],
    }
    payload["pr"] = pr_payload
    status_path.write_text(json.dumps(payload, indent=2))
    update_run_state(run_root, payload)


def _write_human_gate_package(run_root: Path) -> None:
    status_path = run_root / "status.json"
    payload = json.loads(status_path.read_text()) if status_path.exists() else {}
    if not all(str(payload.get(key) or "").strip() for key in ("summary_path", "verification_path", "review_path")):
        return
    package = build_human_gate_package(run_root)
    package_json_path = "human_gate_package.json"
    package_markdown_path = "human_gate_package.md"
    (run_root / package_json_path).write_text(json.dumps(package, indent=2))
    (run_root / package_markdown_path).write_text(render_human_gate_package_markdown(package))

    status_path = run_root / "status.json"
    payload = json.loads(status_path.read_text()) if status_path.exists() else {}
    human_gate = dict(payload.get("human_gate") or {})
    human_gate.update({
        "package_json_path": package_json_path,
        "package_markdown_path": package_markdown_path,
    })
    payload["human_gate"] = human_gate
    status_path.write_text(json.dumps(payload, indent=2))
    update_run_state(run_root, payload)



def write_reviewer_snapshot(run_root: Path, iteration: int, reviewer_result) -> None:
    """Persist reviewer result for a given iteration."""
    run_root.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    reviewer_payload = {
        "iteration": iteration,
        "approved": reviewer_result.approved,
        "findings": reviewer_result.findings,
        "reviewed_at": now,
    }
    artifacts_dir = run_root / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = artifacts_dir / f"reviewer_{iteration}.json"
    snapshot_path.write_text(json.dumps(reviewer_payload, indent=2))

    summary_payload = {
        "approved": reviewer_result.approved,
        "iterations": iteration,
        "findings": reviewer_result.findings,
    }
    (run_root / "reviewer_summary.json").write_text(json.dumps(summary_payload, indent=2))

    status_path = run_root / "status.json"
    payload = json.loads(status_path.read_text()) if status_path.exists() else {}
    payload["reviewer"] = {
        "approved": reviewer_result.approved,
        "iterations": iteration,
        "findings_count": len(reviewer_result.findings),
        "last_reviewed_at": now,
    }
    status_path.write_text(json.dumps(payload, indent=2))
    update_run_state(run_root, payload)


def write_human_gate_decision(
    run_root: Path,
    *,
    status: str,
    decision: str,
    issue_key: str,
    note: str,
) -> None:
    run_root.mkdir(parents=True, exist_ok=True)
    applied_at = datetime.now(timezone.utc).isoformat()
    next_action = {
        "approve": "ready_for_pr",
        "reject": "revise_and_rerun",
    }.get(decision)
    status_path = run_root / "status.json"
    payload = json.loads(status_path.read_text()) if status_path.exists() else {}
    human_gate = dict(payload.get("human_gate") or {})
    human_gate.update({
        "decision": decision,
        "note": note,
        "next_action": next_action,
        "decision_required": False,
        "decision_applied": True,
        "applied_at": applied_at,
    })
    payload.update({
        "status": status,
        "issue_key": issue_key,
        "human_gate": human_gate,
    })
    if decision == "approve":
        required_handoff_fields = {
            "issue_key": payload.get("issue_key"),
            "branch": payload.get("branch"),
            "commit_sha": payload.get("commit_sha"),
            "worktree_path": payload.get("worktree_path"),
            "base_branch": payload.get("base_branch"),
        }
        missing_handoff_fields = [
            field_name
            for field_name, field_value in required_handoff_fields.items()
            if not str(field_value or "").strip()
        ]
        if missing_handoff_fields:
            missing_fields = ", ".join(missing_handoff_fields)
            raise ValueError(
                f"Approved Human Gate decision requires non-empty handoff fields: {missing_fields}"
            )
    (run_root / "human_gate_decision.md").write_text(
        "# Human Gate Decision\n\n"
        f"Issue: {issue_key}\n"
        f"Decision: {decision}\n"
        f"Note: {note}\n"
        f"Next Action: {next_action}\n"
        f"Applied At: {applied_at}\n"
    )
    if decision == "approve":
        (run_root / "pr_handoff.md").write_text(
            "# PR Handoff\n\n"
            f"Issue: {payload.get('issue_key', issue_key)}\n"
            f"Branch: {payload.get('branch', '')}\n"
            f"Worktree: {payload.get('worktree_path', '')}\n"
            f"Base Branch: {payload.get('base_branch', '')}\n"
            f"Commit: {payload.get('commit_sha', '')}\n"
            f"Note: {note}\n"
            f"Next Action: {next_action}\n"
        )
    status_path.write_text(json.dumps(payload, indent=2))
    update_run_state(run_root, payload)
    _write_human_gate_package(run_root)
