from pathlib import Path

from .models import LinearIssue


def write_context_packet(issue: LinearIssue, output_path: Path, selected_comments: list[str]) -> None:
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
    output_path.write_text("\n".join(lines).strip() + "\n")
