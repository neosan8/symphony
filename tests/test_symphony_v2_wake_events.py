import tempfile
import time
import unittest
from pathlib import Path

from symphony_runtime import wake_compat as MODULE


class _FakeResponse:
    status_code = 202

    def raise_for_status(self):
        return None


class _FakeSession:
    def __init__(self):
        self.post_calls = []

    def post(self, url, json=None, timeout=None, headers=None):
        self.post_calls.append(
            {
                "url": url,
                "json": json,
                "timeout": timeout,
                "headers": headers,
            }
        )
        return _FakeResponse()


class _FakeSourceClient:
    def __init__(self):
        self.state_updates = []
        self.comments = []

    def fetch_todo_issues(self):
        return []

    def update_issue_state(self, issue, target):
        self.state_updates.append((issue.issue_id, target))

    def add_completion_comment(self, issue, body):
        self.comments.append((issue.issue_id, body))


class _FakeProcess:
    def __init__(self, pid, returncode):
        self.pid = pid
        self._returncode = returncode

    def poll(self):
        return self._returncode


class SymphonyWakeEventTests(unittest.TestCase):
    def _daemon(self, tmpdir, fallback_poll_interval=120):
        daemon = MODULE.SymphonyDaemon(
            paperclip_api_url=MODULE.DEFAULT_PAPERCLIP_API_URL,
            linear_api_url=MODULE.DEFAULT_LINEAR_API_URL,
            linear_team_id=MODULE.DEFAULT_LINEAR_TEAM_ID,
            source_mode="paperclip",
            dry_run=False,
            poll_interval=30,
            wake_event_url="http://gateway.test/wake",
            fallback_poll_interval=fallback_poll_interval,
            concurrency=1,
            workspace_root=Path(tmpdir),
            log_path=Path(tmpdir) / "symphony_v2.log",
            codex_bin="codex",
            requests_timeout=15,
        )
        daemon.session = _FakeSession()
        daemon.source_clients = {"paperclip": _FakeSourceClient()}
        return daemon

    def _issue(self):
        return MODULE.Issue(
            source="paperclip",
            issue_id="issue-123",
            title="Wake me when finished",
            description="",
            state="in_progress",
            raw={"id": "issue-123", "url": "https://example.test/issues/issue-123"},
        )

    def test_completion_path_posts_completed_wake_event(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            daemon = self._daemon(tmpdir)
            issue = self._issue()
            run = MODULE.IssueRun(issue, Path(tmpdir), _FakeProcess(pid=111, returncode=0))
            daemon.active_runs[issue.run_key] = run

            daemon._reap_finished_runs()

            client = daemon.source_clients["paperclip"]
            self.assertEqual(client.state_updates, [("issue-123", "done")])
            self.assertEqual(client.comments, [("issue-123", MODULE.COMPLETION_COMMENT)])
            self.assertEqual(len(daemon.session.post_calls), 1)
            wake_call = daemon.session.post_calls[0]
            self.assertEqual(wake_call["url"], "http://gateway.test/wake")
            self.assertEqual(wake_call["json"]["outcome"], "completed")
            self.assertEqual(wake_call["json"]["detectedBy"], "process_poll")

    def test_failure_path_posts_failed_wake_event(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            daemon = self._daemon(tmpdir)
            issue = self._issue()
            run = MODULE.IssueRun(issue, Path(tmpdir), _FakeProcess(pid=222, returncode=17))
            daemon.active_runs[issue.run_key] = run

            daemon._reap_finished_runs()

            client = daemon.source_clients["paperclip"]
            self.assertEqual(client.state_updates, [])
            self.assertEqual(client.comments, [])
            self.assertEqual(len(daemon.session.post_calls), 1)
            wake_call = daemon.session.post_calls[0]
            self.assertEqual(wake_call["json"]["outcome"], "failed")
            self.assertEqual(wake_call["json"]["returncode"], 17)
            self.assertEqual(wake_call["json"]["reason"], "worker_exit")

    def test_fallback_check_runs_at_two_minute_cadence_and_emits_stalled_wake(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            daemon = self._daemon(tmpdir, fallback_poll_interval=120)
            issue = self._issue()
            run = MODULE.IssueRun(issue, Path(tmpdir), _FakeProcess(pid=333, returncode=None))
            stale_time = time.time() - 121
            run.started_at = stale_time
            run.last_activity_at = stale_time
            daemon.active_runs[issue.run_key] = run
            daemon._last_fallback_check_at = time.monotonic() - 121

            daemon._run_fallback_check()

            self.assertEqual(len(daemon.session.post_calls), 1)
            wake_call = daemon.session.post_calls[0]
            self.assertEqual(wake_call["json"]["outcome"], "stalled")
            self.assertEqual(wake_call["json"]["detectedBy"], "fallback_poll")
            self.assertEqual(wake_call["json"]["reason"], "no_output_for_120s")

            daemon._run_fallback_check()
            self.assertEqual(len(daemon.session.post_calls), 1)


if __name__ == "__main__":
    unittest.main()
