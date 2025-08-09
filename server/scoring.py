from typing import Any, Dict, Tuple
import os

MINUTES_LONG_RUN = int(os.environ.get("MINUTES_LONG_RUN", "18"))
HIGH_CHURN_LINES = int(os.environ.get("HIGH_CHURN_LINES", "500"))


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def compute_attention(pr: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    additions = pr.get("additions") or 0
    deletions = pr.get("deletions") or 0
    changed_files = pr.get("changed_files") or 0
    draft = bool(pr.get("draft"))
    ci_status = (pr.get("ci_status") or "unknown").lower()
    has_tests = bool(pr.get("has_tests"))
    doc_touch_ratio = float(pr.get("doc_touch_ratio") or 0.0)

    churn = additions + deletions
    churn_factor = clamp(churn / HIGH_CHURN_LINES, 0.0, 1.0)
    churn_score = int(round(30 * churn_factor))

    file_pressure = clamp(changed_files / 20.0, 0.0, 1.0)
    file_score = int(round(20 * file_pressure))

    ci_score = {
        "failure": 25,
        "error": 25,
        "cancelled": 10,
        "pending": 10,
        "in_progress": 10,
        "unknown": 5,
        "success": 0,
        "neutral": 0,
    }.get(ci_status, 5)

    test_score = 0 if has_tests else 15
    draft_penalty = -10 if draft else 0
    docs_penalty = -5 if doc_touch_ratio > 0.5 else 0

    raw_score = churn_score + file_score + ci_score + test_score + draft_penalty + docs_penalty
    score = int(clamp(raw_score, 0, 100))

    factors = {
        "churn_lines": churn,
        "churn_score": churn_score,
        "changed_files": changed_files,
        "file_score": file_score,
        "ci_status": ci_status,
        "ci_score": ci_score,
        "has_tests": has_tests,
        "test_score": test_score,
        "draft": draft,
        "draft_penalty": draft_penalty,
        "doc_touch_ratio": doc_touch_ratio,
        "docs_penalty": docs_penalty,
    }
    return score, factors