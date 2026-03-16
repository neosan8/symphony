from .models import LinearIssue


DISPATCH_LABELS = {"agent-ready", "symphony"}


def is_issue_dispatchable(issue: LinearIssue) -> bool:
    if issue.status.lower() != "todo":
        return False
    return any(label in DISPATCH_LABELS for label in issue.labels)
