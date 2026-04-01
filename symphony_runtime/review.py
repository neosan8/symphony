def pick_review_mode(risk_tier: str) -> list[str]:
    if risk_tier == "high":
        return ["codex", "claude"]
    if risk_tier == "low":
        return ["codex"]
    raise ValueError(f"Unsupported risk tier: {risk_tier}")
