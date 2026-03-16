import sys
import tempfile
import types
import unittest
from pathlib import Path
from importlib.util import module_from_spec, spec_from_file_location


sys.modules.setdefault("requests", types.SimpleNamespace(Session=object))

SPEC = spec_from_file_location("symphony_module", Path(__file__).resolve().parents[1] / "symphony.py")
MODULE = module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class _FakeResponse:
    status_code = 200

    def raise_for_status(self):
        return None


class _FakeSession:
    def __init__(self):
        self.calls = []

    def patch(self, url, json=None, timeout=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        return _FakeResponse()


class IssueStateUpdateTests(unittest.TestCase):
    def _daemon(self, tmpdir):
        daemon = MODULE.SymphonyDaemon(
            api_url=MODULE.DEFAULT_API_URL,
            poll_interval=30,
            concurrency=1,
            workspace_root=Path(tmpdir),
            log_path=Path(tmpdir) / "symphony.log",
            codex_bin="codex",
            requests_timeout=15,
        )
        fake_session = _FakeSession()
        daemon.session = fake_session
        return daemon, fake_session

    def test_update_issue_state_uses_global_issue_endpoint(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            daemon, fake_session = self._daemon(tmpdir)
            issue = MODULE.Issue(
                issue_id="issue-123",
                title="Test issue",
                description="",
                state="todo",
                raw={"id": "issue-123", "assigneeAgentId": "agent-456"},
            )

            daemon._update_issue_state(issue, "in_progress")

            self.assertEqual(len(fake_session.calls), 1)
            self.assertEqual(
                fake_session.calls[0]["url"],
                "http://127.0.0.1:3100/api/issues/issue-123",
            )

    def test_in_progress_includes_assignee_agent_id_when_present(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            daemon, fake_session = self._daemon(tmpdir)
            issue = MODULE.Issue(
                issue_id="issue-123",
                title="Test issue",
                description="",
                state="todo",
                raw={"id": "issue-123", "assigneeAgentId": "agent-456"},
            )

            daemon._update_issue_state(issue, "in_progress")

            self.assertEqual(
                fake_session.calls[0]["json"],
                {"status": "in_progress", "assigneeAgentId": "agent-456"},
            )

    def test_done_does_not_force_assignee_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            daemon, fake_session = self._daemon(tmpdir)
            issue = MODULE.Issue(
                issue_id="issue-123",
                title="Test issue",
                description="",
                state="in_progress",
                raw={"id": "issue-123", "assigneeAgentId": "agent-456"},
            )

            daemon._update_issue_state(issue, "done")

            self.assertEqual(fake_session.calls[0]["json"], {"status": "done"})

    def test_build_logger_closes_previous_file_handlers_before_replacing_them(self):
        with tempfile.TemporaryDirectory() as first_tmpdir, tempfile.TemporaryDirectory() as second_tmpdir:
            first_daemon, _ = self._daemon(first_tmpdir)
            first_file_handlers = [
                handler for handler in first_daemon.logger.handlers if hasattr(handler, "stream")
            ]
            self.assertTrue(first_file_handlers)

            second_daemon, _ = self._daemon(second_tmpdir)

            for handler in first_file_handlers:
                self.assertNotIn(handler, second_daemon.logger.handlers)
                if getattr(handler, "baseFilename", None):
                    self.assertTrue(handler.stream is None or handler.stream.closed)


if __name__ == "__main__":
    unittest.main()
