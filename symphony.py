#!/usr/bin/env python3
"""Poll Paperclip issues and dispatch Codex workers for todo items."""

from __future__ import annotations

import argparse
import json
import logging
import os
import queue
import shlex
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Iterable

import requests


DEFAULT_API_URL = (
    "http://127.0.0.1:3100/api/companies/"
    "bd025116-d2c3-4ad8-9f7a-b308af09f966/issues"
)
DEFAULT_POLL_INTERVAL = 30
DEFAULT_CONCURRENCY = 5
DEFAULT_WORKSPACE_ROOT = Path("/tmp/symphony")
DEFAULT_LOG_PATH = DEFAULT_WORKSPACE_ROOT / "symphony.log"
DEFAULT_REQUEST_TIMEOUT = 15


@dataclass
class Issue:
    issue_id: str
    title: str
    description: str
    state: str
    raw: dict[str, Any]


class IssueRun:
    def __init__(self, issue: Issue, workspace: Path, process: subprocess.Popen[str]) -> None:
        self.issue = issue
        self.workspace = workspace
        self.process = process
        self.started_at = time.time()
        self.stdout_path = workspace / "stdout.log"
        self.stderr_path = workspace / "stderr.log"
        self._threads: list[threading.Thread] = []

    def attach_thread(self, thread: threading.Thread) -> None:
        self._threads.append(thread)

    def wait_for_log_threads(self) -> None:
        for thread in self._threads:
            thread.join(timeout=2)


class SymphonyDaemon:
    def __init__(
        self,
        api_url: str,
        poll_interval: int,
        concurrency: int,
        workspace_root: Path,
        log_path: Path,
        codex_bin: str,
        requests_timeout: int,
    ) -> None:
        self.api_url = api_url
        self.poll_interval = poll_interval
        self.concurrency = concurrency
        self.workspace_root = workspace_root
        self.log_path = log_path
        self.codex_bin = codex_bin
        self.requests_timeout = requests_timeout
        self.stop_event = threading.Event()
        self.active_runs: dict[str, IssueRun] = {}
        self.session = requests.Session()
        self.logger = self._build_logger()
        self.event_queue: queue.Queue[tuple[str, str]] = queue.Queue()

    def _build_logger(self) -> logging.Logger:
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger("symphony")
        logger.setLevel(logging.INFO)
        self._reset_logger_handlers(logger)
        formatter = logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

        file_handler = RotatingFileHandler(
            self.log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        return logger

    @staticmethod
    def _reset_logger_handlers(logger: logging.Logger) -> None:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

    def run(self) -> int:
        self._install_signal_handlers()
        self.logger.info(
            "starting daemon api_url=%s poll_interval=%ss concurrency=%s workspace_root=%s codex_bin=%s",
            self.api_url,
            self.poll_interval,
            self.concurrency,
            self.workspace_root,
            self.codex_bin,
        )
        try:
            while not self.stop_event.is_set():
                cycle_started = time.monotonic()
                self._reap_finished_runs()
                self._poll_and_dispatch()
                self._drain_event_queue()
                elapsed = time.monotonic() - cycle_started
                remaining = max(0.0, self.poll_interval - elapsed)
                self.stop_event.wait(remaining)
        finally:
            self._shutdown_active_runs()
            self._drain_event_queue()
            self.logger.info("daemon stopped")
        return 0

    def _install_signal_handlers(self) -> None:
        def handle_signal(signum: int, _: Any) -> None:
            self.logger.info("received signal=%s, shutting down", signum)
            self.stop_event.set()

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

    def _poll_and_dispatch(self) -> None:
        issues = self._fetch_todo_issues()
        todo_ids = {issue.issue_id for issue in issues}
        self.logger.info(
            "poll complete total_todo=%s active_runs=%s", len(issues), len(self.active_runs)
        )

        for issue_id, run in list(self.active_runs.items()):
            if issue_id not in todo_ids:
                self.logger.info(
                    "issue no longer todo, terminating run issue_id=%s pid=%s",
                    issue_id,
                    run.process.pid,
                )
                self._terminate_run(run, reason="state_changed")

        available_slots = self.concurrency - len(self.active_runs)
        if available_slots <= 0:
            self.logger.debug("dispatch skipped no_capacity=%s", self.concurrency)
            return

        for issue in issues:
            if issue.issue_id in self.active_runs:
                continue
            if available_slots <= 0:
                break
            try:
                self._start_run(issue)
                available_slots -= 1
            except Exception:
                self.logger.exception("failed to start run issue_id=%s", issue.issue_id)

    def _fetch_todo_issues(self) -> list[Issue]:
        self.logger.debug("fetching issues url=%s", self.api_url)
        response = self.session.get(self.api_url, timeout=self.requests_timeout)
        response.raise_for_status()
        payload = response.json()
        issues = [issue for issue in self._iter_issues(payload) if self._is_todo(issue)]
        issues.sort(key=lambda issue: issue.issue_id)
        return issues

    def _iter_issues(self, payload: Any) -> Iterable[Issue]:
        items: Any
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            for key in ("issues", "data", "results", "items"):
                if isinstance(payload.get(key), list):
                    items = payload[key]
                    break
            else:
                items = [payload]
        else:
            raise ValueError(f"unsupported payload type: {type(payload)!r}")

        for item in items:
            if not isinstance(item, dict):
                self.logger.warning("skipping non-object issue payload=%r", item)
                continue
            issue = self._normalize_issue(item)
            if issue is None:
                continue
            yield issue

    def _normalize_issue(self, item: dict[str, Any]) -> Issue | None:
        issue_id = self._first_string(item, ("id", "issueId", "uuid"))
        if not issue_id:
            self.logger.warning("skipping issue without id payload=%s", self._compact_json(item))
            return None
        title = self._first_string(item, ("title", "name", "summary")) or "(untitled)"
        description = self._first_string(item, ("description", "body", "content")) or ""
        state = self._extract_state(item)
        return Issue(
            issue_id=issue_id,
            title=title,
            description=description,
            state=state,
            raw=item,
        )

    def _extract_state(self, item: dict[str, Any]) -> str:
        for key in ("state", "status"):
            value = item.get(key)
            if isinstance(value, str):
                return value
            if isinstance(value, dict):
                for nested_key in ("name", "value", "label"):
                    nested_value = value.get(nested_key)
                    if isinstance(nested_value, str):
                        return nested_value
        return ""

    def _is_todo(self, issue: Issue) -> bool:
        normalized = issue.state.strip().lower()
        return normalized == "todo"

    def _update_issue_state(self, issue: Issue, status: str) -> None:
        """PATCH the Paperclip API to update issue status.

        The list endpoint is company-scoped, but single-issue writes go through
        the global issue endpoint: /api/issues/{issue_id}.
        For `in_progress`, Paperclip requires the issue to have an assignee, so
        we include assigneeAgentId / assigneeUserId from the polled issue when
        available.
        Failures are logged but never propagated so the daemon continues.
        """
        issue_id = issue.issue_id
        api_root = self.api_url.split("/api/", 1)[0]
        url = f"{api_root}/api/issues/{issue_id}"
        payload = {"status": status}
        if status == "in_progress":
            assignee_agent_id = self._first_string(issue.raw, ("assigneeAgentId",))
            assignee_user_id = self._first_string(issue.raw, ("assigneeUserId",))
            if assignee_agent_id:
                payload["assigneeAgentId"] = assignee_agent_id
            if assignee_user_id:
                payload["assigneeUserId"] = assignee_user_id
        try:
            response = self.session.patch(
                url,
                json=payload,
                timeout=self.requests_timeout,
            )
            response.raise_for_status()
            self.logger.info(
                "issue state updated issue_id=%s status=%s http=%s",
                issue_id,
                status,
                response.status_code,
            )
        except Exception as exc:
            self.logger.warning(
                "failed to update issue state issue_id=%s status=%s error=%s",
                issue_id,
                status,
                exc,
            )

    def _start_run(self, issue: Issue) -> None:
        workspace = self.workspace_root / issue.issue_id
        workspace.mkdir(parents=True, exist_ok=True)
        metadata_path = workspace / "issue.json"
        metadata_path.write_text(
            json.dumps(issue.raw, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self._update_issue_state(issue, "in_progress")

        prompt = self._build_prompt(issue, metadata_path)
        cmd = [self.codex_bin, "exec", "--full-auto", prompt]
        self.logger.info(
            "starting codex issue_id=%s cwd=%s cmd=%s",
            issue.issue_id,
            workspace,
            shlex.join(cmd),
        )

        stdout_handle = open(workspace / "stdout.log", "a", encoding="utf-8", buffering=1)
        stderr_handle = open(workspace / "stderr.log", "a", encoding="utf-8", buffering=1)
        process = subprocess.Popen(
            cmd,
            cwd=workspace,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        run = IssueRun(issue=issue, workspace=workspace, process=process)
        self.active_runs[issue.issue_id] = run

        stdout_thread = threading.Thread(
            target=self._stream_output,
            args=(run, process.stdout, stdout_handle, logging.INFO, "stdout"),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=self._stream_output,
            args=(run, process.stderr, stderr_handle, logging.WARNING, "stderr"),
            daemon=True,
        )
        run.attach_thread(stdout_thread)
        run.attach_thread(stderr_thread)
        stdout_thread.start()
        stderr_thread.start()

    def _build_prompt(self, issue: Issue, metadata_path: Path) -> str:
        issue_url = self._first_string(issue.raw, ("url", "htmlUrl", "permalink")) or ""
        return (
            "You are working on a Symphony issue dispatch.\n\n"
            f"Issue ID: {issue.issue_id}\n"
            f"Title: {issue.title}\n"
            f"State: {issue.state or 'todo'}\n"
            f"URL: {issue_url}\n\n"
            "Description:\n"
            f"{issue.description or '(no description)'}\n\n"
            f"Raw issue JSON is available at {metadata_path}.\n"
            "Work inside the current directory and complete the issue."
        )

    def _stream_output(
        self,
        run: IssueRun,
        stream: Any,
        file_handle: Any,
        level: int,
        stream_name: str,
    ) -> None:
        """Stream child process output to per-issue log files only.

        Child output (stdout/stderr) is written exclusively to the per-issue
        log files (stdout.log / stderr.log).  We deliberately do NOT forward
        every line to the daemon logger — Codex is extremely verbose and
        doing so is the primary source of runaway daemon log growth.
        A line count summary is emitted at DEBUG level when the stream closes.
        """
        line_count = 0
        try:
            if stream is None:
                return
            for line in iter(stream.readline, ""):
                file_handle.write(line)
                file_handle.flush()
                line_count += 1
        finally:
            if stream is not None:
                stream.close()
            file_handle.close()
            self.logger.debug(
                "stream closed issue_id=%s pid=%s %s lines=%s",
                run.issue.issue_id,
                run.process.pid,
                stream_name,
                line_count,
            )

    def _reap_finished_runs(self) -> None:
        for issue_id, run in list(self.active_runs.items()):
            returncode = run.process.poll()
            if returncode is None:
                continue
            run.wait_for_log_threads()
            duration = time.time() - run.started_at
            self.logger.info(
                "run finished issue_id=%s pid=%s returncode=%s duration=%.1fs",
                issue_id,
                run.process.pid,
                returncode,
                duration,
            )
            terminal_state = "done" if returncode == 0 else "error"
            self._update_issue_state(run.issue, terminal_state)
            del self.active_runs[issue_id]

    def _terminate_run(self, run: IssueRun, reason: str) -> None:
        process = run.process
        if process.poll() is not None:
            return
        self.logger.info(
            "terminating process issue_id=%s pid=%s reason=%s",
            run.issue.issue_id,
            process.pid,
            reason,
        )
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.logger.warning(
                "process did not exit after terminate, killing issue_id=%s pid=%s",
                run.issue.issue_id,
                process.pid,
            )
            process.kill()
            process.wait(timeout=5)

    def _shutdown_active_runs(self) -> None:
        if not self.active_runs:
            return
        self.logger.info("shutting down active runs count=%s", len(self.active_runs))
        for run in list(self.active_runs.values()):
            try:
                self._terminate_run(run, reason="daemon_shutdown")
            except Exception:
                self.logger.exception(
                    "error terminating run issue_id=%s pid=%s",
                    run.issue.issue_id,
                    run.process.pid,
                )
        self._reap_finished_runs()

    def _drain_event_queue(self) -> None:
        while True:
            try:
                message_type, payload = self.event_queue.get_nowait()
            except queue.Empty:
                return
            self.logger.info("event type=%s payload=%s", message_type, payload)

    @staticmethod
    def _first_string(item: dict[str, Any], keys: tuple[str, ...]) -> str | None:
        for key in keys:
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _compact_json(value: Any) -> str:
        try:
            return json.dumps(value, sort_keys=True, separators=(",", ":"))
        except TypeError:
            return repr(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Symphony issue polling daemon")
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--poll-interval", type=int, default=DEFAULT_POLL_INTERVAL)
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--workspace-root", type=Path, default=DEFAULT_WORKSPACE_ROOT)
    parser.add_argument("--log-path", type=Path, default=DEFAULT_LOG_PATH)
    parser.add_argument("--codex-bin", default=os.environ.get("CODEX_BIN", "codex"))
    parser.add_argument("--request-timeout", type=int, default=DEFAULT_REQUEST_TIMEOUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    daemon = SymphonyDaemon(
        api_url=args.api_url,
        poll_interval=args.poll_interval,
        concurrency=args.concurrency,
        workspace_root=args.workspace_root,
        log_path=args.log_path,
        codex_bin=args.codex_bin,
        requests_timeout=args.request_timeout,
    )
    return daemon.run()


if __name__ == "__main__":
    raise SystemExit(main())
