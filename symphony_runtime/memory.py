"""Lightweight task memory layer for Symphony v2.

Uses OpenAI embeddings (text-embedding-3-small) and stores vectors in a
JSONL file. No native dependencies — works with Python 3.13+.

All functions are silent-fallback: errors are logged but never raised,
so a broken memory layer never blocks task execution.
"""
from __future__ import annotations

import json
import logging
import math
import os
import traceback
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MEMORY_PATH = Path.home() / "Documents" / "symphony" / "memory_db" / "tasks.jsonl"
_EMBED_MODEL = "text-embedding-3-small"


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _get_embedding(text: str) -> list[float] | None:
    """Get embedding via OpenAI API. Returns None on failure."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        logger.debug("memory: OPENAI_API_KEY not set, skipping embedding")
        return None
    try:
        import urllib.request
        payload = json.dumps({
            "model": _EMBED_MODEL,
            "input": text[:8000],
        }).encode()
        req = urllib.request.Request(
            "https://api.openai.com/v1/embeddings",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        return data["data"][0]["embedding"]
    except Exception:
        logger.debug("memory: embedding request failed\n%s", traceback.format_exc())
        return None


def _load_records() -> list[dict[str, Any]]:
    if not _MEMORY_PATH.exists():
        return []
    records = []
    try:
        for line in _MEMORY_PATH.read_text(errors="replace").splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
    except Exception:
        logger.debug("memory: failed to load records\n%s", traceback.format_exc())
    return records


def search_memory(query: str, top_k: int = 3) -> list[dict]:
    """Search for similar past tasks.

    Returns list of dicts: {issue_id, title, summary, outcome, score}.
    Returns [] on any error or empty DB. Never raises.
    """
    if not query or not query.strip():
        return []
    try:
        records = _load_records()
        if not records:
            return []
        query_vec = _get_embedding(query)
        if query_vec is None:
            return []
        scored = []
        for rec in records:
            vec = rec.get("vector")
            if not vec:
                continue
            score = _cosine_similarity(query_vec, vec)
            scored.append((score, rec))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "issue_id": rec.get("issue_id", ""),
                "title": rec.get("title", ""),
                "summary": rec.get("summary", ""),
                "outcome": rec.get("outcome", "unknown"),
                "score": round(score, 4),
            }
            for score, rec in scored[:top_k]
        ]
    except Exception:
        logger.debug("memory: search failed\n%s", traceback.format_exc())
        return []


def store_memory(
    issue_id: str,
    title: str,
    summary: str,
    outcome: str,
    tags: list[str] | None = None,
) -> None:
    """Store a completed task in memory.

    outcome: "success" | "failed" | "partial"
    Never raises — silent fallback on error.
    """
    if not issue_id or not summary:
        return
    try:
        text = f"{title} {summary}".strip()
        vec = _get_embedding(text)
        if vec is None:
            return
        _MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "issue_id": issue_id,
            "title": title or "",
            "summary": summary[:1000],
            "outcome": outcome or "unknown",
            "tags": tags or [],
            "vector": vec,
        }
        with _MEMORY_PATH.open("a") as f:
            f.write(json.dumps(record) + "\n")
        logger.debug("memory: stored task %s (%s)", issue_id, outcome)
    except Exception:
        logger.debug("memory: store failed for %s\n%s", issue_id, traceback.format_exc())
