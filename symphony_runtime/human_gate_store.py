from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from symphony_runtime.config import SymphonyConfig


@dataclass(frozen=True)
class HumanGateRecord:
    issue_id: str
    issue_key: str
    branch: str
    commit_sha: str
    status: str
    decision_required: bool
    decision_applied: bool
    recommendation: str | None = None
    decision: str | None = None
    note: str | None = None
    next_action: str | None = None
    applied_at: str | None = None
    run_root: Path | None = None


@dataclass(frozen=True)
class HumanGateContext:
    issue_id: str
    issue_key: str
    branch: str
    commit_sha: str
    run_root: Path | None = None


@dataclass(frozen=True)
class HumanGateScanIssue:
    run_root: Path
    message: str


@dataclass(frozen=True)
class HumanGateScanResult:
    pending_runs: list[HumanGateContext]
    issues: list[HumanGateScanIssue]


@dataclass(frozen=True)
class ReadyForPrRecord:
    issue_id: str
    issue_key: str
    branch: str
    commit_sha: str
    base_branch: str
    worktree_path: Path
    run_root: Path | None = None


@dataclass(frozen=True)
class PrOpenedRecord:
    issue_id: str
    issue_key: str
    branch: str
    commit_sha: str
    worktree_path: Path
    base_branch: str
    pr_url: str
    pr_opened_at: str
    run_root: Path


@dataclass(frozen=True)
class ReadyForPrScanResult:
    ready_runs: list[HumanGateRecord]
    issues: list[HumanGateScanIssue]


@dataclass(frozen=True)
class PrOpenedScanResult:
    records: list[PrOpenedRecord]
    issues: list[HumanGateScanIssue]


def resolve_run_root(config: SymphonyConfig, run_ref: str) -> Path:
    run_root = Path(run_ref)
    if run_root.is_absolute():
        return run_root

    resolved_run_root = (config.runs_root / run_root).resolve(strict=False)
    runs_root = config.runs_root.resolve(strict=False)
    try:
        resolved_run_root.relative_to(runs_root)
    except ValueError as exc:
        raise ValueError(f"Run ref must stay within runs_root {runs_root}: {run_ref}") from exc
    return resolved_run_root


def load_human_gate_record(run_root: Path) -> HumanGateRecord:
    status_path = run_root / "status.json"
    payload = json.loads(status_path.read_text())

    required_fields = {
        "issue_id": payload.get("issue_id"),
        "issue_key": payload.get("issue_key"),
        "branch": payload.get("branch"),
        "commit_sha": payload.get("commit_sha"),
    }
    missing_fields = [name for name, value in required_fields.items() if not isinstance(value, str) or not value]
    if missing_fields:
        raise ValueError(
            f"Missing or invalid Human Gate context fields in {status_path}: {', '.join(missing_fields)}"
        )

    human_gate = payload.get("human_gate")
    if not isinstance(human_gate, dict):
        raise ValueError(f"Missing or invalid human_gate payload in {status_path}")

    if not isinstance(human_gate.get("decision_required"), bool):
        raise ValueError(f"Missing or invalid human_gate.decision_required in {status_path}")
    if not isinstance(human_gate.get("decision_applied"), bool):
        raise ValueError(f"Missing or invalid human_gate.decision_applied in {status_path}")

    decision = human_gate.get("decision")
    next_action = human_gate.get("next_action")
    applied_at = human_gate.get("applied_at")
    if human_gate["decision_applied"]:
        if not isinstance(decision, str) or not decision:
            raise ValueError(f"Missing or invalid human_gate.decision in {status_path}")
        if not isinstance(next_action, str) or not next_action:
            raise ValueError(f"Missing or invalid human_gate.next_action in {status_path}")
        if not isinstance(applied_at, str) or not applied_at:
            raise ValueError(f"Missing or invalid human_gate.applied_at in {status_path}")

    recommendation = human_gate.get("recommendation")
    note = human_gate.get("note")
    if recommendation is not None and not isinstance(recommendation, str):
        raise ValueError(f"Missing or invalid human_gate.recommendation in {status_path}")
    if decision is not None and not isinstance(decision, str):
        raise ValueError(f"Missing or invalid human_gate.decision in {status_path}")
    if note is not None and not isinstance(note, str):
        raise ValueError(f"Missing or invalid human_gate.note in {status_path}")
    if next_action is not None and not isinstance(next_action, str):
        raise ValueError(f"Missing or invalid human_gate.next_action in {status_path}")
    if applied_at is not None and not isinstance(applied_at, str):
        raise ValueError(f"Missing or invalid human_gate.applied_at in {status_path}")

    status = payload.get("status")
    if not isinstance(status, str) or not status:
        raise ValueError(f"Missing or invalid status in {status_path}")

    return HumanGateRecord(
        issue_id=required_fields["issue_id"],
        issue_key=required_fields["issue_key"],
        branch=required_fields["branch"],
        commit_sha=required_fields["commit_sha"],
        status=status,
        decision_required=human_gate["decision_required"],
        decision_applied=human_gate["decision_applied"],
        recommendation=recommendation,
        decision=decision,
        note=note,
        next_action=next_action,
        applied_at=applied_at,
        run_root=run_root,
    )


def load_human_gate_record_from_ref(config: SymphonyConfig, run_ref: str) -> HumanGateRecord:
    return load_human_gate_record(resolve_run_root(config, run_ref))


def _load_status_payload(run_root: Path) -> tuple[Path, dict]:
    status_path = run_root / "status.json"
    return status_path, json.loads(status_path.read_text())


def _load_pr_handoff_record(run_root: Path) -> tuple[Path, dict, HumanGateRecord, ReadyForPrRecord]:
    status_path, payload = _load_status_payload(run_root)
    record = load_human_gate_record(run_root)

    if record.status != "done":
        raise ValueError(f"Expected ready-for-pr status in {status_path}")
    if not record.decision_applied:
        raise ValueError(f"Expected applied Human Gate decision in {status_path}")
    if record.decision != "approve":
        raise ValueError(f"Expected approved Human Gate decision in {status_path}")

    worktree_path = payload.get("worktree_path")
    base_branch = payload.get("base_branch")

    required_fields = {
        "branch": record.branch,
        "commit_sha": record.commit_sha,
        "worktree_path": worktree_path,
        "base_branch": base_branch,
    }
    missing_fields = [name for name, value in required_fields.items() if not isinstance(value, str) or not value]
    if missing_fields:
        raise ValueError(
            f"Missing or invalid ready-for-pr fields in {status_path}: {', '.join(missing_fields)}"
        )

    return status_path, payload, record, ReadyForPrRecord(
        issue_id=record.issue_id,
        issue_key=record.issue_key,
        branch=record.branch,
        commit_sha=record.commit_sha,
        base_branch=base_branch,
        worktree_path=Path(worktree_path),
        run_root=run_root,
    )


def load_ready_for_pr_record(run_root: Path) -> ReadyForPrRecord:
    status_path, _payload, record, ready_record = _load_pr_handoff_record(run_root)
    if record.next_action != "ready_for_pr":
        raise ValueError(f"Expected ready_for_pr next action in {status_path}")
    return ready_record


def load_pr_opened_record(run_root: Path) -> PrOpenedRecord:
    status_path, payload, record, ready_record = _load_pr_handoff_record(run_root)
    if record.next_action != "pr_opened":
        raise ValueError(f"Expected pr_opened next action in {status_path}")

    pr_payload = payload.get("pr")
    if not isinstance(pr_payload, dict):
        raise ValueError(f"Missing or invalid pr payload in {status_path}")

    pr_url = pr_payload.get("url")
    pr_opened_at = pr_payload.get("opened_at")
    required_fields = {
        "url": pr_url,
        "opened_at": pr_opened_at,
    }
    missing_fields = [name for name, value in required_fields.items() if not isinstance(value, str) or not value]
    if missing_fields:
        raise ValueError(f"Missing or invalid pr fields in {status_path}: {', '.join(missing_fields)}")

    return PrOpenedRecord(
        issue_id=ready_record.issue_id,
        issue_key=ready_record.issue_key,
        branch=ready_record.branch,
        commit_sha=ready_record.commit_sha,
        worktree_path=ready_record.worktree_path,
        base_branch=ready_record.base_branch,
        pr_url=pr_url,
        pr_opened_at=pr_opened_at,
        run_root=run_root,
    )


def load_human_gate_context(run_root: Path) -> HumanGateContext:
    status_path = run_root / "status.json"
    record = load_human_gate_record(run_root)

    if record.status != "human_gate":
        raise ValueError(f"Expected pending Human Gate status in {status_path}")
    if not record.decision_required or record.decision_applied:
        raise ValueError(f"Expected pending Human Gate decision in {status_path}")

    return HumanGateContext(
        issue_id=record.issue_id,
        issue_key=record.issue_key,
        branch=record.branch,
        commit_sha=record.commit_sha,
        run_root=run_root,
    )


def _looks_like_non_pending_human_gate_run(run_root: Path) -> bool:
    status_path = run_root / "status.json"
    payload = json.loads(status_path.read_text())

    if payload.get("status") != "human_gate":
        return True

    human_gate = payload.get("human_gate")
    if not isinstance(human_gate, dict):
        return False

    decision_required = human_gate.get("decision_required")
    decision_applied = human_gate.get("decision_applied")
    if isinstance(decision_required, bool) and isinstance(decision_applied, bool):
        return not decision_required or decision_applied
    return False


def scan_pending_human_gate_runs(config: SymphonyConfig) -> HumanGateScanResult:
    pending_runs: list[HumanGateContext] = []
    issues: list[HumanGateScanIssue] = []
    if not config.runs_root.exists():
        return HumanGateScanResult(pending_runs=pending_runs, issues=issues)

    for run_root in sorted(path for path in config.runs_root.iterdir() if path.is_dir()):
        try:
            context = load_human_gate_context(run_root)
        except FileNotFoundError:
            continue
        except json.JSONDecodeError as exc:
            issues.append(HumanGateScanIssue(run_root=run_root, message=str(exc)))
            continue
        except ValueError as exc:
            if str(exc).startswith("Expected pending Human Gate "):
                continue
            try:
                if _looks_like_non_pending_human_gate_run(run_root):
                    continue
            except FileNotFoundError:
                continue
            except json.JSONDecodeError as decode_exc:
                issues.append(HumanGateScanIssue(run_root=run_root, message=str(decode_exc)))
                continue
            issues.append(HumanGateScanIssue(run_root=run_root, message=str(exc)))
            continue
        pending_runs.append(context)

    return HumanGateScanResult(pending_runs=pending_runs, issues=issues)


def list_pending_human_gate_runs(config: SymphonyConfig) -> list[HumanGateContext]:
    return scan_pending_human_gate_runs(config).pending_runs


def _is_ready_for_pr_record(record: HumanGateRecord) -> bool:
    return (
        record.status == "done"
        and record.decision_applied
        and record.decision == "approve"
        and record.next_action == "ready_for_pr"
    )


def scan_ready_for_pr_runs(config: SymphonyConfig) -> ReadyForPrScanResult:
    ready_runs: list[HumanGateRecord] = []
    issues: list[HumanGateScanIssue] = []
    if not config.runs_root.exists():
        return ReadyForPrScanResult(ready_runs=ready_runs, issues=issues)

    for run_root in sorted(path for path in config.runs_root.iterdir() if path.is_dir()):
        try:
            record = load_human_gate_record(run_root)
        except FileNotFoundError:
            continue
        except json.JSONDecodeError as exc:
            issues.append(HumanGateScanIssue(run_root=run_root, message=str(exc)))
            continue
        except ValueError as exc:
            issues.append(HumanGateScanIssue(run_root=run_root, message=str(exc)))
            continue

        if _is_ready_for_pr_record(record):
            ready_runs.append(record)

    return ReadyForPrScanResult(ready_runs=ready_runs, issues=issues)


def list_ready_for_pr_runs(config: SymphonyConfig) -> list[HumanGateRecord]:
    return scan_ready_for_pr_runs(config).ready_runs


def scan_pr_opened_runs(config: SymphonyConfig) -> PrOpenedScanResult:
    records: list[PrOpenedRecord] = []
    issues: list[HumanGateScanIssue] = []
    if not config.runs_root.exists():
        return PrOpenedScanResult(records=records, issues=issues)

    for run_root in sorted(path for path in config.runs_root.iterdir() if path.is_dir()):
        try:
            record = load_pr_opened_record(run_root)
        except FileNotFoundError:
            continue
        except json.JSONDecodeError as exc:
            issues.append(HumanGateScanIssue(run_root=run_root, message=str(exc)))
            continue
        except ValueError as exc:
            issues.append(HumanGateScanIssue(run_root=run_root, message=str(exc)))
            continue
        records.append(record)

    return PrOpenedScanResult(records=records, issues=issues)


def list_pr_opened_runs(config: SymphonyConfig) -> list[PrOpenedRecord]:
    return scan_pr_opened_runs(config).records
