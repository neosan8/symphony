import tempfile
import unittest
from pathlib import Path

from symphony_runtime.config import SymphonyConfig
from symphony_runtime.daemon import SymphonyRuntime
from symphony_runtime.models import LinearIssue
from symphony_runtime.repo_map import RepoMapping


class RuntimeSelectionTests(unittest.TestCase):
    def make_runtime(self, tmpdir: str) -> SymphonyRuntime:
        return SymphonyRuntime(
            config=SymphonyConfig(
                workspace_root=Path(tmpdir),
                config_root=Path(tmpdir) / "config",
                runs_root=Path(tmpdir) / "runs",
                worktrees_root=Path(tmpdir) / "worktrees",
            )
        )

    def make_issue(
        self,
        identifier: str,
        *,
        project_key: str = "symphony",
        status: str = "Todo",
        labels: list[str] | None = None,
    ) -> LinearIssue:
        return LinearIssue(
            id=f"issue-id-{identifier.lower()}",
            identifier=identifier,
            title=f"Issue {identifier}",
            description="Body",
            status=status,
            labels=labels or ["agent-ready"],
            project_key=project_key,
        )

    def make_mapping(self, project_key: str = "symphony") -> RepoMapping:
        return RepoMapping(
            project_key=project_key,
            repo_key=project_key,
            repo_path="/Users/neosan/.openclaw/workspace/worktrees/symphony-v2",
            base_branch="main",
        )

    def test_select_dispatchable_issue_returns_issue_and_repo_mapping(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = self.make_runtime(tmpdir)
            issue = self.make_issue("LIN-42")
            mapping = self.make_mapping()

            selected_issue, selected_mapping = runtime.select_dispatchable_issue([issue], {"symphony": mapping})

            self.assertEqual(selected_issue.identifier, "LIN-42")
            self.assertEqual(selected_mapping.repo_key, "symphony")

    def test_select_dispatchable_issue_returns_first_qualifying_issue(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = self.make_runtime(tmpdir)
            first_issue = self.make_issue("LIN-42")
            second_issue = self.make_issue("LIN-43")
            mapping = self.make_mapping()

            selected_issue, selected_mapping = runtime.select_dispatchable_issue(
                [first_issue, second_issue],
                {"symphony": mapping},
            )

            self.assertEqual(selected_issue.identifier, "LIN-42")
            self.assertEqual(selected_mapping.repo_key, "symphony")

    def test_select_dispatchable_issue_skips_issue_without_repo_mapping(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = self.make_runtime(tmpdir)
            unmapped_issue = self.make_issue("LIN-42", project_key="unknown")
            mapped_issue = self.make_issue("LIN-43")
            mapping = self.make_mapping()

            selected_issue, selected_mapping = runtime.select_dispatchable_issue(
                [unmapped_issue, mapped_issue],
                {"symphony": mapping},
            )

            self.assertEqual(selected_issue.identifier, "LIN-43")
            self.assertEqual(selected_mapping.repo_key, "symphony")

    def test_select_dispatchable_issue_skips_issue_with_repo_mapping_that_is_not_dispatchable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = self.make_runtime(tmpdir)
            ineligible_issue = self.make_issue("LIN-42", status="In Progress")
            dispatchable_issue = self.make_issue("LIN-43")
            mapping = self.make_mapping()

            selected_issue, selected_mapping = runtime.select_dispatchable_issue(
                [ineligible_issue, dispatchable_issue],
                {"symphony": mapping},
            )

            self.assertEqual(selected_issue.identifier, "LIN-43")
            self.assertEqual(selected_mapping.repo_key, "symphony")

    def test_select_dispatchable_issue_raises_lookup_error_when_nothing_qualifies(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = self.make_runtime(tmpdir)
            unmapped_issue = self.make_issue("LIN-42", project_key="unknown")
            ineligible_issue = self.make_issue("LIN-43", status="In Progress")
            mapping = self.make_mapping()

            with self.assertRaisesRegex(LookupError, "No dispatchable issue found"):
                runtime.select_dispatchable_issue(
                    [unmapped_issue, ineligible_issue],
                    {"symphony": mapping},
                )
