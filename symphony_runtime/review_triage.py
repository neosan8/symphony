from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class ReviewFinding:
    source: str
    finding_id: str
    author: str | None
    body: str
    is_blocking: bool = False


@dataclass(frozen=True)
class ReviewTriageSummary:
    total_findings: int
    blocking_count: int
    unresolved_findings: list[ReviewFinding]


def summarize_review_payload(review_json: str) -> ReviewTriageSummary:
    """Summarize unresolved review comments and blocking review state."""
    payload = json.loads(review_json)
    if not isinstance(payload, dict):
        raise ValueError(
            "review payload must be a JSON object with optional 'comments' and 'reviews' lists"
        )

    comments = payload.get("comments", [])
    reviews = payload.get("reviews", [])
    if not isinstance(comments, list) or not isinstance(reviews, list):
        raise ValueError(
            "review payload must be a JSON object with optional 'comments' and 'reviews' lists"
        )

    unresolved_findings: list[ReviewFinding] = []
    blocking_count = 0

    for comment in comments:
        comment = _review_entry(comment)
        body = _normalize_body(comment.get("body"))
        if not body:
            continue
        unresolved_findings.append(
            ReviewFinding(
                source="comment",
                finding_id=str(comment.get("id", "")),
                author=_author_login(comment.get("author")),
                body=body,
            )
        )

    for review in reviews:
        review = _review_entry(review)
        is_blocking = review.get("state") == "CHANGES_REQUESTED"
        if is_blocking:
            blocking_count += 1

        body = _normalize_body(review.get("body"))
        if not body:
            continue
        unresolved_findings.append(
            ReviewFinding(
                source="review",
                finding_id=str(review.get("id", "")),
                author=_author_login(review.get("author")),
                body=body,
                is_blocking=is_blocking,
            )
        )

    return ReviewTriageSummary(
        total_findings=len(unresolved_findings),
        blocking_count=blocking_count,
        unresolved_findings=unresolved_findings,
    )


def _review_entry(entry: object) -> dict[str, object]:
    if not isinstance(entry, dict):
        raise ValueError(
            "review payload comments and reviews must contain only JSON objects"
        )
    return entry


def _normalize_body(body: object) -> str:
    if not isinstance(body, str):
        return ""
    return body.strip()


def _author_login(author: object) -> str | None:
    if not isinstance(author, dict):
        return None
    login = author.get("login")
    return login if isinstance(login, str) and login else None

