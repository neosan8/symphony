from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess

from symphony_runtime.config import SymphonyConfig
from symphony_runtime.config_loader import load_repo_map as load_repo_map_file
from symphony_runtime.context_packet import write_context_packet
from symphony_runtime.dispatch import is_issue_dispatchable
from symphony_runtime.executor import build_codex_command, run_codex_command
from symphony_runtime.git_handoff import resolve_head_commit
from symphony_runtime.linear_client import LinearClient
from symphony_runtime.human_gate import VALID_HUMAN_GATE_DECISIONS
from symphony_runtime.human_gate_package import build_human_gate_package
from symphony_runtime.human_gate_store import (
    load_human_gate_context,
    load_pr_opened_record,
    load_ready_for_pr_record,
    resolve_run_root,
)
from symphony_runtime.pr_create import create_pull_request, ensure_ready_for_pr
from symphony_runtime.pr_reviews import fetch_pr_review_comments
from symphony_runtime.linear_sync import (
    build_blocked_comment,
    build_human_gate_approved_comment,
    build_human_gate_comment,
    build_human_gate_rejected_comment,
    build_started_comment,
)
from symphony_runtime.models import ExecutionResult, LinearIssue, ReviewerResult, RunStatus
from symphony_runtime.preflight import run_preflight
from symphony_runtime.repo_contract import load_repo_contract as load_repo_contract_file
from symphony_runtime.repo_map import RepoMapping
from symphony_runtime.reviewer import run_reviewer
from symphony_runtime.run_store import (
    initialize_run_state,
    write_human_gate_decision,
    write_human_gate_handoff,
    write_human_gate_preview_state,
    write_merge_preparation_artifacts,
    write_pr_opened,
    write_pr_review_acknowledgement,
    write_pr_review_snapshot,
    write_reviewer_snapshot,
    write_summary_artifacts,
)
from symphony_runtime.secret_requirements import check_required_secrets
from symphony_runtime.worktree import ensure_issue_worktree


@dataclass
class SymphonyRuntime:
    config: SymphonyConfig

    def ensure_workspace_roots(self) -> None:
        self.config.config_root.mkdir(parents=True, exist_ok=True)
        self.config.runs_root.mkdir(parents=True, exist_ok=True)
        self.config.worktrees_root.mkdir(parents=True, exist_ok=True)

    def fetch_candidate_issues(self) -> list[LinearIssue]:
        api_key = os.environ.get("LINEAR_API_KEY", "").strip()
        team_id = os.environ.get("LINEAR_TEAM_ID", "").strip()
        if not api_key or not team_id:
            raise RuntimeError("LINEAR_API_KEY and LINEAR_TEAM_ID must be set for runtime issue fetch")
        return LinearClient(api_key=api_key, team_id=team_id).fetch_candidate_issues()

    def load_repo_map(self) -> dict[str, RepoMapping]:
        return load_repo_map_file(self.config.config_root / "repos.json")

    def load_repo_contract(self, mapping: RepoMapping) -> dict:
        return load_repo_contract_file(Path(mapping.repo_path))

    def get_linear_client(self) -> LinearClient:
        client = getattr(self, "linear_client", None)
        if client is not None:
            return client

        api_key = os.environ.get("LINEAR_API_KEY", "").strip()
        team_id = os.environ.get("LINEAR_TEAM_ID", "").strip()
        if not api_key or not team_id:
            raise RuntimeError("LINEAR_API_KEY and LINEAR_TEAM_ID must be set for Linear sync")

        client = LinearClient(api_key=api_key, team_id=team_id)
        self.linear_client = client
        return client

    def get_linear_state_map(self) -> dict[str, str]:
        state_map = getattr(self, "linear_state_map", None)
        if state_map is None:
            state_map = self.get_linear_client().fetch_workflow_states()
            self.linear_state_map = state_map
        return state_map

    def sync_status(self, issue_id: str, state_name: str) -> bool:
        if not issue_id:
            return False

        state_id = self.get_linear_state_map().get(state_name)
        if state_id is None:
            raise LookupError(f"Linear workflow state not found: {state_name}")

        return self.get_linear_client().update_issue_status(issue_id, state_id)

    def sync_started(self, issue_id: str, issue_key: str, branch: str) -> bool:
        if not issue_id:
            return False
        comment = build_started_comment(issue_key, branch)
        return self.get_linear_client().add_comment(issue_id, comment)

    def sync_blocked(self, issue_id: str, issue_key: str, reason: str) -> bool:
        if not issue_id:
            return False
        comment = build_blocked_comment(issue_key, reason)
        return self.get_linear_client().add_comment(issue_id, comment)

    def sync_human_gate(
        self,
        issue_id: str,
        issue_key: str,
        branch: str,
        commit_sha: str,
        recommendation: str,
        summary: str,
        verification: str,
        review: str,
    ) -> bool:
        if not issue_id:
            return False
        comment = build_human_gate_comment(
            issue_key=issue_key,
            branch=branch,
            commit_sha=commit_sha,
            recommendation=recommendation,
            summary=summary,
            verification=verification,
            review=review,
        )
        return self.get_linear_client().add_comment(issue_id, comment)

    def apply_human_gate_decision(
        self,
        issue_id: str,
        issue_key: str,
        decision: str,
        note: str,
        run_root: Path,
    ) -> None:
        if decision not in VALID_HUMAN_GATE_DECISIONS:
            raise ValueError(f"Unknown Human Gate decision: {decision}")

        if decision == "approve":
            comment = build_human_gate_approved_comment(issue_key, note)
            target_status = "Done"
            local_status = RunStatus.DONE.value
        else:
            comment = build_human_gate_rejected_comment(issue_key, note)
            target_status = "Blocked"
            local_status = RunStatus.BLOCKED.value

        comment_synced = self.get_linear_client().add_comment(issue_id, comment)
        if not comment_synced:
            raise RuntimeError(
                f"Failed to sync Human Gate {decision} comment to Linear for {issue_key}"
            )

        status_synced = self.sync_status(issue_id, target_status)
        if not status_synced:
            raise RuntimeError(
                f"Failed to sync Human Gate {decision} status {target_status} to Linear for {issue_key}"
            )

        write_human_gate_decision(
            run_root,
            status=local_status,
            decision=decision,
            issue_key=issue_key,
            note=note,
        )

    def apply_human_gate_decision_from_run(self, run_ref: str, decision: str, note: str) -> None:
        run_root = resolve_run_root(self.config, run_ref)
        context = load_human_gate_context(run_root)
        self.apply_human_gate_decision(
            issue_id=context.issue_id,
            issue_key=context.issue_key,
            decision=decision,
            note=note,
            run_root=run_root,
        )

    def create_pr_from_run(self, run_ref: str) -> str:
        run_root = resolve_run_root(self.config, run_ref)
        record = load_ready_for_pr_record(run_root)
        ensure_ready_for_pr(
            record.worktree_path,
            expected_commit=record.commit_sha,
            expected_branch=record.branch,
        )
        pr_url = create_pull_request(
            worktree_path=record.worktree_path,
            base_branch=record.base_branch,
            head_branch=record.branch,
            title=record.issue_key,
            body_path=run_root / "pr_handoff.md",
        )
        write_pr_opened(run_root, pr_url)
        return pr_url

    def refresh_pr_reviews_from_run(self, run_ref: str) -> None:
        run_root = resolve_run_root(self.config, run_ref)
        record = load_pr_opened_record(run_root)
        review_json = fetch_pr_review_comments(record.pr_url, record.worktree_path)
        write_pr_review_snapshot(run_root, review_json)

    def get_pr_review_status_from_run(self, run_ref: str) -> dict:
        run_root = resolve_run_root(self.config, run_ref)
        resolved_run_root = run_root.resolve(strict=False)
        runs_root = self.config.runs_root.resolve(strict=False)
        try:
            resolved_run_root.relative_to(runs_root)
        except ValueError as exc:
            raise ValueError(f"Run ref must stay within runs_root {runs_root}: {run_ref}") from exc
        run_root = resolved_run_root
        record = load_pr_opened_record(run_root)
        status_path = run_root / "status.json"
        state_path = run_root / "state.json"
        status_payload = json.loads(status_path.read_text())
        state_payload = json.loads(state_path.read_text())
        status_pr_payload = status_payload.get("pr")
        state_pr_payload = state_payload.get("pr")
        if not isinstance(status_pr_payload, dict):
            raise ValueError(f"Missing or invalid pr payload in {status_path}")
        if not isinstance(state_pr_payload, dict):
            raise ValueError(f"Missing or invalid pr payload in {state_path}")

        review_fields = (
            "review_fetched_at",
            "review_comments_path",
            "review_findings_path",
            "review_diff_path",
            "review_triage_path",
        )
        for field_name in review_fields:
            value = status_pr_payload.get(field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(
                    "Run is not in a review-snapshotted state; missing PR review metadata in "
                    f"{status_path}: {field_name}"
                )
            state_value = state_pr_payload.get(field_name)
            if state_value != value:
                raise ValueError(
                    f"PR review metadata mismatch between {status_path} and {state_path}: {field_name}"
                )

        blocking_review_count = status_pr_payload.get("blocking_review_count")
        if not isinstance(blocking_review_count, int) or blocking_review_count < 0:
            raise ValueError(
                "Run is not in a review-snapshotted state; missing PR review metadata in "
                f"{status_path}: blocking_review_count"
            )
        if state_pr_payload.get("blocking_review_count") != blocking_review_count:
            raise ValueError(
                f"PR review metadata mismatch between {status_path} and {state_path}: blocking_review_count"
            )

        for field_name in ("newly_introduced_findings_count", "resolved_findings_count"):
            value = status_pr_payload.get(field_name)
            if not isinstance(value, int) or value < 0:
                raise ValueError(
                    "Run is not in a review-snapshotted state; missing PR review metadata in "
                    f"{status_path}: {field_name}"
                )
            if state_pr_payload.get(field_name) != value:
                raise ValueError(
                    f"PR review metadata mismatch between {status_path} and {state_path}: {field_name}"
                )

        review_comments_path = Path(status_pr_payload["review_comments_path"])
        review_findings_path = Path(status_pr_payload["review_findings_path"])
        review_diff_path = Path(status_pr_payload["review_diff_path"])
        review_triage_path = Path(status_pr_payload["review_triage_path"])
        for artifact_path in (review_comments_path, review_findings_path, review_diff_path, review_triage_path):
            if artifact_path.is_absolute() or not artifact_path.parts:
                raise ValueError(f"Invalid PR review artifact path in {status_path}: {artifact_path}")
            resolved_artifact_path = run_root / artifact_path
            if not resolved_artifact_path.exists():
                raise ValueError(f"Missing PR review artifact referenced by {status_path}: {artifact_path}")

        unresolved_findings_count = self._load_unresolved_findings_count(
            run_root / review_findings_path,
            status_path,
        )

        previous_review_findings_path = status_pr_payload.get("previous_review_findings_path")
        if previous_review_findings_path is not None:
            if state_pr_payload.get("previous_review_findings_path") != previous_review_findings_path:
                raise ValueError(
                    f"PR review metadata mismatch between {status_path} and {state_path}: previous_review_findings_path"
                )
            previous_review_findings_path = Path(previous_review_findings_path)
            if previous_review_findings_path.is_absolute() or not previous_review_findings_path.parts:
                raise ValueError(
                    f"Invalid PR review artifact path in {status_path}: {previous_review_findings_path}"
                )
            resolved_previous_path = run_root / previous_review_findings_path
            if not resolved_previous_path.exists():
                raise ValueError(
                    f"Missing PR review artifact referenced by {status_path}: {previous_review_findings_path}"
                )
        else:
            resolved_previous_path = None

        return {
            "run_ref": run_root.name,
            "issue_key": record.issue_key,
            "branch": record.branch,
            "commit_sha": record.commit_sha,
            "pr_url": record.pr_url,
            "pr_opened_at": record.pr_opened_at,
            "review_fetched_at": status_pr_payload["review_fetched_at"],
            "review_comments_path": str(run_root / review_comments_path),
            "previous_review_findings_path": (
                str(resolved_previous_path) if resolved_previous_path is not None else None
            ),
            "review_findings_path": str(run_root / review_findings_path),
            "review_diff_path": str(run_root / review_diff_path),
            "review_triage_path": str(run_root / review_triage_path),
            "blocking_review_count": blocking_review_count,
            "newly_introduced_findings_count": status_pr_payload["newly_introduced_findings_count"],
            "resolved_findings_count": status_pr_payload["resolved_findings_count"],
            "unresolved_findings_count": unresolved_findings_count,
        }

    def acknowledge_pr_reviews_from_run(self, run_ref: str, state: str, note: str) -> None:
        self.get_pr_review_status_from_run(run_ref)
        run_root = resolve_run_root(self.config, run_ref)
        write_pr_review_acknowledgement(run_root, state, note)

    def get_human_gate_package_from_run(self, run_ref: str) -> dict:
        run_root = resolve_run_root(self.config, run_ref)
        resolved_run_root = run_root.resolve(strict=False)
        runs_root = self.config.runs_root.resolve(strict=False)
        try:
            resolved_run_root.relative_to(runs_root)
        except ValueError as exc:
            raise ValueError(f"Run ref must stay within runs_root {runs_root}: {run_ref}") from exc
        run_root = resolved_run_root

        status_path = run_root / "status.json"
        state_path = run_root / "state.json"
        status_payload = json.loads(status_path.read_text())
        state_payload = json.loads(state_path.read_text())
        status_human_gate = status_payload.get("human_gate")
        state_human_gate = state_payload.get("human_gate")
        if not isinstance(status_human_gate, dict):
            raise ValueError(f"Missing or invalid human_gate payload in {status_path}")
        if not isinstance(state_human_gate, dict):
            raise ValueError(f"Missing or invalid human_gate payload in {state_path}")

        package_paths: dict[str, Path] = {}
        for key in ("package_json_path", "package_markdown_path"):
            value = status_human_gate.get(key)
            if not isinstance(value, str) or not value:
                raise ValueError(f"Missing or invalid {key} in {status_path}")
            if state_human_gate.get(key) != value:
                raise ValueError(
                    f"Human Gate package metadata mismatch between {status_path} and {state_path}: {key}"
                )
            artifact_path = Path(value)
            if artifact_path.is_absolute() or not artifact_path.parts:
                raise ValueError(f"Invalid {key} in {status_path}: {value}")
            resolved_artifact_path = (run_root / artifact_path).resolve(strict=False)
            try:
                resolved_artifact_path.relative_to(run_root)
            except ValueError as exc:
                raise ValueError(f"Invalid {key} in {status_path}: {value}") from exc
            if not resolved_artifact_path.exists():
                raise ValueError(f"Missing Human Gate package artifact referenced by {status_path}: {value}")
            package_paths[key] = resolved_artifact_path

        package_payload = json.loads(package_paths["package_json_path"].read_text())
        rebuilt_package = build_human_gate_package(run_root)
        comparable_package_payload = dict(package_payload)
        comparable_rebuilt_package = dict(rebuilt_package)
        comparable_package_payload.pop("run_root", None)
        comparable_rebuilt_package.pop("run_root", None)
        if comparable_package_payload != comparable_rebuilt_package:
            raise ValueError(f"Human Gate package artifact mismatch in {package_paths['package_json_path']}")

        return {
            "run_ref": run_root.name,
            "issue_key": rebuilt_package["issue_key"],
            "branch": rebuilt_package.get("branch", status_payload.get("branch", "")),
            "recommendation": rebuilt_package["recommendation"],
            "verification_path": str(run_root / rebuilt_package["verification_path"]),
            "review_path": str(run_root / rebuilt_package["review_path"]),
            "blocking_review_count": int(rebuilt_package.get("blocking_review_count", 0)),
            "unresolved_findings_count": int(rebuilt_package.get("unresolved_findings_count", 0)),
            "acknowledgement_state": rebuilt_package.get("acknowledgement_state", "unacknowledged"),
            "package_json_path": str(package_paths["package_json_path"]),
            "package_markdown_path": str(package_paths["package_markdown_path"]),
        }

    def prepare_merge_from_run(self, run_ref: str) -> dict:
        review_status = self.get_pr_review_status_from_run(run_ref)
        if review_status["blocking_review_count"] != 0:
            raise ValueError("prepare_merge_from_run requires blocking_review_count == 0")

        run_root = resolve_run_root(self.config, run_ref).resolve(strict=False)
        status_path = run_root / "status.json"
        state_path = run_root / "state.json"
        status_payload = json.loads(status_path.read_text())
        state_payload = json.loads(state_path.read_text())

        for artifact_key in ("summary_path", "verification_path", "review_path"):
            status_value = status_payload.get(artifact_key)
            state_value = state_payload.get(artifact_key)
            if not isinstance(status_value, str) or not status_value:
                raise ValueError(f"prepare_merge_from_run requires {artifact_key}")
            if state_value != status_value:
                raise ValueError(
                    f"prepare_merge_from_run requires matching {artifact_key} metadata in status.json and state.json"
                )
            if not (run_root / status_value).exists():
                raise ValueError(f"prepare_merge_from_run requires existing {status_value}")

        status_pr_payload = status_payload.get("pr")
        state_pr_payload = state_payload.get("pr")
        if not isinstance(status_pr_payload, dict) or not isinstance(state_pr_payload, dict):
            raise ValueError("prepare_merge_from_run requires opened PR state")

        acknowledgement = status_pr_payload.get("review_acknowledgement")
        state_acknowledgement = state_pr_payload.get("review_acknowledgement")
        if not isinstance(acknowledgement, dict) or not isinstance(state_acknowledgement, dict):
            raise ValueError("prepare_merge_from_run requires review acknowledgement")
        if acknowledgement != state_acknowledgement:
            raise ValueError("prepare_merge_from_run requires matching review acknowledgement metadata")
        acknowledgement_state = acknowledgement.get("state")
        if acknowledgement_state != "addressed":
            raise ValueError("prepare_merge_from_run requires acknowledgement state addressed")

        human_gate = status_payload.get("human_gate")
        state_human_gate = state_payload.get("human_gate")
        if not isinstance(human_gate, dict) or not isinstance(state_human_gate, dict):
            raise ValueError("prepare_merge_from_run requires Human Gate package metadata")

        package_paths: dict[str, str] = {}
        for key in ("package_markdown_path", "package_json_path"):
            package_path = human_gate.get(key)
            if state_human_gate.get(key) != package_path:
                raise ValueError("prepare_merge_from_run requires matching Human Gate package metadata")
            if not isinstance(package_path, str) or not package_path:
                raise ValueError("prepare_merge_from_run requires Human Gate package metadata")
            if not (run_root / package_path).exists():
                raise ValueError(f"prepare_merge_from_run requires existing {package_path}")
            package_paths[key] = package_path

        merge_preparation_payload = {
            "run_ref": review_status["run_ref"],
            "issue_key": review_status["issue_key"],
            "branch": review_status["branch"],
            "commit_sha": review_status["commit_sha"],
            "pr_url": review_status["pr_url"],
            "summary_path": status_payload["summary_path"],
            "verification_path": status_payload["verification_path"],
            "review_path": status_payload["review_path"],
            "human_gate_package_path": package_paths["package_markdown_path"],
            "human_gate_package_json_path": package_paths["package_json_path"],
            "blocking_review_count": review_status["blocking_review_count"],
            "unresolved_findings_count": review_status["unresolved_findings_count"],
            "newly_introduced_findings_count": review_status["newly_introduced_findings_count"],
            "resolved_findings_count": review_status["resolved_findings_count"],
            "acknowledgement_state": acknowledgement_state,
        }
        write_merge_preparation_artifacts(run_root, merge_preparation_payload)

        return {
            "run_ref": review_status["run_ref"],
            "issue_key": review_status["issue_key"],
            "branch": review_status["branch"],
            "commit_sha": review_status["commit_sha"],
            "pr_url": review_status["pr_url"],
            "summary_path": str(run_root / status_payload["summary_path"]),
            "verification_path": str(run_root / status_payload["verification_path"]),
            "review_path": str(run_root / status_payload["review_path"]),
            "human_gate_package_path": str(run_root / package_paths["package_markdown_path"]),
            "human_gate_package_json_path": str(run_root / package_paths["package_json_path"]),
            "blocking_review_count": review_status["blocking_review_count"],
            "acknowledgement_state": acknowledgement_state,
            "merge_preparation_path": str(run_root / "merge_preparation.md"),
        }

    @staticmethod
    def _load_unresolved_findings_count(review_findings_path: Path, status_path: Path) -> int:
        findings_payload = json.loads(review_findings_path.read_text())
        unresolved_findings = findings_payload.get("unresolved_findings")
        if isinstance(unresolved_findings, list):
            return len(unresolved_findings)

        total_findings = findings_payload.get("total_findings")
        if isinstance(total_findings, int) and total_findings >= 0:
            return total_findings

        raise ValueError(
            "Run is not in a review-snapshotted state; missing unresolved findings metadata in "
            f"{status_path}: {review_findings_path.name}"
        )

    def run_once_dry(self) -> str:
        issues = self.fetch_candidate_issues()
        repo_map = self.load_repo_map()
        issue, mapping = self.select_dispatchable_issue(issues, repo_map)
        repo_contract = self.load_repo_contract(mapping)
        prep = self.prepare_issue_run(issue, mapping, repo_contract)

        return self.write_human_gate_preview(
            run_root=prep["run_root"],
            issue_key=issue.identifier,
            branch=prep["branch_name"],
            commit_sha="dry-run",
            recommendation="review",
            summary=f"Dry-run preview prepared for {issue.title}",
            verification=self._format_preflight(prep["preflight"]),
            review="Dry-run only; Codex command prepared but not executed.",
        )

    def run_once_execute(self) -> str:
        issues = self.fetch_candidate_issues()
        repo_map = self.load_repo_map()
        issue, mapping = self.select_dispatchable_issue(issues, repo_map)
        repo_contract = self.load_repo_contract(mapping)
        prep = self.prepare_issue_run(issue, mapping, repo_contract)
        if not prep["preflight"].ok:
            self.sync_blocked(issue.id, issue.identifier, prep["preflight"].reason or "preflight failed")
            self.sync_status(issue.id, "Blocked")
        else:
            self.sync_started(issue.id, issue.identifier, prep["branch_name"])
            self.sync_status(issue.id, "In Progress")

        max_iterations = self.config.reviewer_max_iterations if self.config.reviewer_enabled else 1
        reviewer_result: ReviewerResult | None = None

        for iteration in range(1, max_iterations + 1):
            execution = self.execute_prepared_run(
                issue_key=issue.identifier,
                run_root=prep["run_root"],
                worktree_path=prep["worktree_path"],
                branch_name=prep["branch_name"],
                command=prep["command"],
                preflight_ok=prep["preflight"].ok,
            )

            if not self.config.reviewer_enabled:
                break

            logs_root = prep["run_root"] / "logs"
            logs_root.mkdir(parents=True, exist_ok=True)
            reviewer_result = run_reviewer(
                worktree_path=execution.worktree_path,
                context_path=prep["run_root"] / "context.md",
                stdout_path=logs_root / f"reviewer_{iteration}.log",
                stderr_path=logs_root / f"reviewer_{iteration}_err.log",
                model=self.config.reviewer_model,
            )
            reviewer_result = ReviewerResult(
                approved=reviewer_result.approved,
                findings=reviewer_result.findings,
                raw_output=reviewer_result.raw_output,
                iterations=iteration,
            )
            write_reviewer_snapshot(prep["run_root"], iteration, reviewer_result)

            if reviewer_result.approved:
                break

            if iteration < max_iterations:
                prep = self._inject_review_findings(prep, issue, reviewer_result.findings)

        verification = self._build_execution_verification(execution)
        review = self._build_execution_review(execution)
        if reviewer_result is not None and not reviewer_result.approved:
            review += "\n\nReviewer findings (unresolved after max iterations):\n"
            for finding in reviewer_result.findings:
                review += f"- BLOCKING: {finding}\n"
        summary = self._build_execution_summary(issue.title, execution.return_code)
        commit_sha = self._resolve_handoff_commit(execution.worktree_path)
        self.write_summary_for_execution(
            execution=execution,
            summary=summary,
            verification=verification,
            review=review,
        )
        preview = self.write_human_gate_preview(
            run_root=execution.run_root,
            issue_key=issue.identifier,
            branch=execution.branch_name,
            commit_sha=commit_sha,
            recommendation="review",
            summary=summary,
            verification=verification,
            review=review,
        )
        write_human_gate_handoff(
            execution.run_root,
            issue_id=issue.id,
            issue_key=issue.identifier,
            branch=execution.branch_name,
            worktree_path=str(execution.worktree_path),
            base_branch=prep["base_branch"],
            commit_sha=commit_sha,
            recommendation="review",
        )
        self.sync_human_gate(
            issue_id=issue.id,
            issue_key=issue.identifier,
            branch=execution.branch_name,
            commit_sha=commit_sha,
            recommendation="review",
            summary=summary,
            verification=verification,
            review=review,
        )

        # Store task result in memory for future reference
        from .memory import store_memory  # noqa: PLC0415
        try:
            stdout_snippet = ""
            if execution.stdout_path.exists():
                stdout_snippet = execution.stdout_path.read_text(errors="replace")[:500]
            mem_summary = stdout_snippet.strip() or summary
            store_memory(
                issue_id=issue.identifier,
                title=issue.title,
                summary=mem_summary,
                outcome="success" if execution.return_code == 0 else "failed",
            )
        except Exception:
            pass  # memory store must never break the main flow

        return preview

    def select_dispatchable_issue(
        self,
        issues: list[LinearIssue],
        repo_map: dict[str, RepoMapping],
    ) -> tuple[LinearIssue, RepoMapping]:
        for issue in issues:
            mapping = repo_map.get(issue.project_key)
            if mapping is None:
                continue
            if is_issue_dispatchable(issue):
                return issue, mapping
        raise LookupError("No dispatchable issue found for configured repositories")

    def prepare_issue_run(
        self,
        issue: LinearIssue,
        mapping: RepoMapping,
        repo_contract: dict,
    ) -> dict:
        run_id = self._build_run_id(issue.identifier)
        run_root = self.config.runs_root / run_id
        initialize_run_state(run_root, issue.identifier, mapping.repo_key)

        worktree_path = self.config.worktrees_root / run_id
        repo_path = Path(mapping.repo_path)
        branch_name = self._build_branch_name(repo_path, run_id)
        verified_base_branch = self._resolve_base_branch(repo_path, mapping.base_branch)
        ensure_issue_worktree(
            repo_path,
            worktree_path,
            branch_name=branch_name,
            base_branch=verified_base_branch,
        )

        context_path = run_root / "context.md"
        from .memory import search_memory  # noqa: PLC0415
        memory_ctx = search_memory(f"{issue.title} {issue.description or ''}")
        write_context_packet(issue, context_path, selected_comments=[], memory_context=memory_ctx)

        secrets_ready, missing_secrets = check_required_secrets(repo_contract)
        preflight = run_preflight(
            repo_root=worktree_path,
            repo_contract=repo_contract,
            context_ready=context_path.exists(),
            secrets_ready=secrets_ready,
            missing_secrets=missing_secrets,
        )
        command = build_codex_command(worktree_path, context_path)

        return {
            "run_root": run_root,
            "worktree_path": worktree_path,
            "branch_name": branch_name,
            "base_branch": verified_base_branch,
            "command": command,
            "preflight": preflight,
        }

    def execute_prepared_run(
        self,
        issue_key: str,
        run_root: Path,
        worktree_path: Path,
        branch_name: str,
        command: list[str],
        preflight_ok: bool,
    ) -> ExecutionResult:
        if not preflight_ok:
            raise ValueError(f"Cannot execute prepared run for {issue_key}: preflight failed")

        logs_root = run_root / "logs"
        logs_root.mkdir(parents=True, exist_ok=True)
        stdout_path = logs_root / "stdout.log"
        stderr_path = logs_root / "stderr.log"
        stdout_path.touch(exist_ok=True)
        stderr_path.touch(exist_ok=True)

        return_code = run_codex_command(
            command=command,
            worktree_path=worktree_path,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )
        return ExecutionResult(
            issue_key=issue_key,
            run_root=run_root,
            worktree_path=worktree_path,
            branch_name=branch_name,
            command=tuple(command),
            return_code=return_code,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            preflight_ok=preflight_ok,
        )

    def write_summary_for_execution(
        self,
        execution: ExecutionResult,
        summary: str,
        verification: str,
        review: str,
    ) -> None:
        write_summary_artifacts(
            run_root=execution.run_root,
            summary=summary,
            verification=verification,
            review=review,
            status_payload={
                "status": RunStatus.HUMAN_GATE.value,
                "issue_key": execution.issue_key,
                "branch": execution.branch_name,
                "return_code": execution.return_code,
                "preflight_ok": execution.preflight_ok,
                "stdout_path": str(execution.stdout_path),
                "stderr_path": str(execution.stderr_path),
            },
        )

    def write_human_gate_preview(
        self,
        run_root: Path,
        issue_key: str,
        branch: str,
        commit_sha: str,
        recommendation: str,
        summary: str,
        verification: str,
        review: str,
    ) -> str:
        preview = build_human_gate_comment(
            issue_key=issue_key,
            branch=branch,
            commit_sha=commit_sha,
            recommendation=recommendation,
            summary=summary,
            verification=verification,
            review=review,
        )
        (run_root / "human_gate.md").write_text(preview)
        write_human_gate_preview_state(
            run_root=run_root,
            issue_key=issue_key,
            branch=branch,
            commit_sha=commit_sha,
            recommendation=recommendation,
        )
        return preview

    @staticmethod
    def _build_run_id(issue_identifier: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", issue_identifier.lower()).strip("-")
        return slug or "run"

    @staticmethod
    def _format_preflight(preflight) -> str:
        return "Preflight passed" if preflight.ok else f"Preflight blocked: {preflight.reason}"

    @staticmethod
    def _build_execution_summary(issue_title: str, return_code: int) -> str:
        if return_code == 0:
            return f"Execution finished for {issue_title}"
        return f"Execution failed for {issue_title}"

    @staticmethod
    def _build_execution_verification(execution: ExecutionResult) -> str:
        if execution.return_code == 0:
            return "Codex execution finished successfully."
        return f"Codex execution exited with code {execution.return_code}."

    @staticmethod
    def _build_execution_review(execution: ExecutionResult) -> str:
        return (
            f"Review stdout at {execution.stdout_path}\n"
            f"Review stderr at {execution.stderr_path}"
        )

    @staticmethod
    def _resolve_handoff_commit(worktree_path: Path) -> str:
        try:
            return resolve_head_commit(worktree_path)
        except RuntimeError:
            return "unresolved-head"

    @staticmethod
    def _resolve_base_branch(repo_path: Path, base_branch: str) -> str:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", base_branch],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return base_branch
        stderr = (result.stderr or "").strip()
        detail = f": {stderr}" if stderr else ""
        raise LookupError(
            f"Configured base branch {base_branch!r} could not be verified in {repo_path}{detail}"
        )

    @classmethod
    def _build_branch_name(cls, repo_path: Path, run_id: str) -> str:
        subprocess.run(["git", "worktree", "prune"], cwd=repo_path, check=True)
        base_name = f"feature/{run_id}"
        branch_name = base_name
        suffix = 2
        while cls._ref_exists(repo_path, branch_name):
            branch_name = f"{base_name}-{suffix}"
            suffix += 1
        return branch_name

    @staticmethod
    def _ref_exists(repo_path: Path, ref_name: str) -> bool:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", ref_name],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    @staticmethod
    def _inject_review_findings(
        prep: dict,
        issue: LinearIssue,
        findings: list[str],
    ) -> dict:
        """Re-write the context packet with review findings injected."""
        context_path = prep["run_root"] / "context.md"
        from .memory import search_memory  # noqa: PLC0415
        memory_ctx = search_memory(f"{issue.title} {issue.description or ''}")
        write_context_packet(
            issue,
            context_path,
            selected_comments=[],
            memory_context=memory_ctx,
            review_findings=findings,
        )
        command = build_codex_command(prep["worktree_path"], context_path)
        updated = dict(prep)
        updated["command"] = command
        return updated
