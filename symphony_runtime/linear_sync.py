def build_started_comment(issue_key: str, branch: str) -> str:
    return f"Execution started for {issue_key}\nBranch: {branch}"


def build_blocked_comment(issue_key: str, reason: str) -> str:
    return f"Execution blocked for {issue_key}\nReason: {reason}"


def build_human_gate_approved_comment(issue_key: str, note: str) -> str:
    return f"Human Gate approved for {issue_key}\nNote: {note}"


def build_human_gate_rejected_comment(issue_key: str, note: str) -> str:
    return f"Human Gate rejected for {issue_key}\nNote: {note}"


def build_human_gate_comment(
    issue_key: str,
    branch: str,
    commit_sha: str,
    recommendation: str,
    summary: str,
    verification: str,
    review: str,
) -> str:
    return "\n".join(
        [
            f"Human Gate for {issue_key}",
            f"Recommendation: {recommendation}",
            f"Branch: {branch}",
            f"Commit: {commit_sha}",
            "",
            "Summary:",
            summary,
            "",
            "Verification:",
            verification,
            "",
            "Review:",
            review,
        ]
    )
