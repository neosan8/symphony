from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_PAPERCLIP_API_URL = "http://127.0.0.1:3100/api/issues"
DEFAULT_LINEAR_API_URL = "https://api.linear.app/graphql"
DEFAULT_LINEAR_TEAM_ID = ""
COMPLETION_COMMENT = "Implemented and ready for review."


@dataclass
class Issue:
    source: str
    issue_id: str
    title: str
    description: str
    state: str
    raw: dict[str, Any]

    @property
    def run_key(self) -> str:
        return f"{self.source}:{self.issue_id}"


@dataclass
class IssueRun:
    issue: Issue
    workspace: Path
    process: Any
    started_at: float = field(default_factory=time.time)
    last_activity_at: float = field(default_factory=time.time)


class SymphonyDaemon:
    def __init__(
        self,
        *,
        paperclip_api_url: str,
        linear_api_url: str,
        linear_team_id: str,
        source_mode: str,
        dry_run: bool,
        poll_interval: int,
        wake_event_url: str | None,
        fallback_poll_interval: int,
        concurrency: int,
        workspace_root: Path,
        log_path: Path,
        codex_bin: str,
        requests_timeout: int,
    ) -> None:
        self.paperclip_api_url = paperclip_api_url
        self.linear_api_url = linear_api_url
        self.linear_team_id = linear_team_id
        self.source_mode = source_mode
        self.dry_run = dry_run
        self.poll_interval = poll_interval
        self.wake_event_url = wake_event_url
        self.fallback_poll_interval = fallback_poll_interval
        self.concurrency = concurrency
        self.workspace_root = workspace_root
        self.log_path = log_path
        self.codex_bin = codex_bin
        self.requests_timeout = requests_timeout
        self.session = self._build_session()
        self.source_clients: dict[str, Any] = {}
        self.active_runs: dict[str, IssueRun] = {}
        self._last_fallback_check_at = time.monotonic()

    def _build_session(self) -> Any:
        try:
            import requests  # type: ignore
        except ModuleNotFoundError:
            return None
        return requests.Session()

    def _reap_finished_runs(self) -> None:
        for run_key, run in list(self.active_runs.items()):
            returncode = run.process.poll()
            if returncode is None:
                continue

            if returncode == 0:
                client = self.source_clients.get(run.issue.source)
                if client is not None:
                    client.update_issue_state(run.issue, "done")
                    client.add_completion_comment(run.issue, COMPLETION_COMMENT)
                self._post_wake_event(
                    issue=run.issue,
                    outcome="completed",
                    detected_by="process_poll",
                )
            else:
                self._post_wake_event(
                    issue=run.issue,
                    outcome="failed",
                    detected_by="process_poll",
                    returncode=returncode,
                    reason="worker_exit",
                )

            self.active_runs.pop(run_key, None)

    def _run_fallback_check(self) -> None:
        now_monotonic = time.monotonic()
        if now_monotonic - self._last_fallback_check_at < self.fallback_poll_interval:
            return
        self._last_fallback_check_at = now_monotonic

        now = time.time()
        for run in self.active_runs.values():
            if run.process.poll() is not None:
                continue
            if now - run.last_activity_at < self.fallback_poll_interval:
                continue
            self._post_wake_event(
                issue=run.issue,
                outcome="stalled",
                detected_by="fallback_poll",
                reason=f"no_output_for_{self.fallback_poll_interval}s",
            )

    def _post_wake_event(
        self,
        *,
        issue: Issue,
        outcome: str,
        detected_by: str,
        reason: str | None = None,
        returncode: int | None = None,
    ) -> None:
        if not self.wake_event_url or self.session is None:
            return

        payload: dict[str, Any] = {
            "issueId": issue.issue_id,
            "outcome": outcome,
            "detectedBy": detected_by,
        }
        if reason is not None:
            payload["reason"] = reason
        if returncode is not None:
            payload["returncode"] = returncode

        self.session.post(self.wake_event_url, json=payload, timeout=self.requests_timeout)
