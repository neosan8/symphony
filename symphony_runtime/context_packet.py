from pathlib import Path

from .models import LinearIssue


def write_context_packet(
    issue: LinearIssue,
    output_path: Path,
    selected_comments: list[str],
    memory_context: list[dict] | None = None,
) -> None:
    lines = [
        f"# {issue.identifier}: {issue.title}",
        "",
        "## Description",
        issue.description,
        "",
        "## Links",
        *[f"- {link}" for link in issue.links],
        "",
        "## Selected Comments",
        *[f"- {comment}" for comment in selected_comments],
    ]
    if memory_context:
        lines += [
            "",
            "## Relevant Past Experience",
            "",
            "These are similar tasks completed before. Use them as reference:",
            "",
        ]
        for entry in memory_context:
            issue_id = entry.get("issue_id", "?")
            summary = entry.get("summary", "").strip()
            outcome = entry.get("outcome", "unknown")
            lines.append(f"- [{issue_id}] {summary} ({outcome})")

    output_path.write_text("\n".join(lines).strip() + "\n")
