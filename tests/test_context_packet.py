import tempfile
import unittest
from pathlib import Path

from symphony_runtime.context_packet import write_context_packet
from symphony_runtime.models import LinearIssue


class ContextPacketTests(unittest.TestCase):
    def test_write_context_packet_includes_title_description_and_links(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "context.md"
            issue = LinearIssue(
                id="issue-id-123",
                identifier="LIN-42",
                title="Fix wake comment",
                description="Make Human Gate output cleaner",
                status="Todo",
                labels=["agent-ready"],
                project_key="symphony",
                comments=["Ignore this unless marked"],
                links=["https://example.test/spec"],
            )
            write_context_packet(issue, output_path, selected_comments=["Important comment"])
            text = output_path.read_text()
            self.assertIn("Fix wake comment", text)
            self.assertIn("Human Gate", text)
            self.assertIn("Important comment", text)
            self.assertNotIn("Ignore this unless marked", text)
