from dataclasses import dataclass


@dataclass
class Scores:
    code_quality: float
    verbosity: float
    efficiency: float
    stability: float
    robustness: float
    clean_code: float
    reusability: float
    ingenuity: float
    attention: float


def clamp(value: float, lo: float = 0.0, hi: float = 10.0) -> float:
    return max(lo, min(hi, float(value)))


def score_pr(pr: dict) -> Scores:
    # Defensive extraction with defaults for a minimal PR dict
    additions = int(pr.get("additions", 0) or 0)
    deletions = int(pr.get("deletions", 0) or 0)
    changed_files = int(pr.get("changed_files", 0) or 0)
    has_tests = bool(pr.get("has_tests", False))
    doc_touch_ratio = float(pr.get("doc_touch_ratio", 0.0) or 0.0)
    draft = bool(pr.get("draft", False))
    state = pr.get("state", "open") or "open"

    churn = additions + deletions

    # Size penalty steps
    if churn < 50:
        size_penalty = 0
    elif churn < 200:
        size_penalty = 2
    elif churn < 600:
        size_penalty = 4
    else:
        size_penalty = 6

    code_quality = clamp(9 - size_penalty + (1 if has_tests else -1))
    verbosity = clamp(5 + (doc_touch_ratio * 5) - (churn / 800.0))
    efficiency = clamp(7 - (churn / 400.0))
    stability = clamp((8 if has_tests else 5) + (2 if state == "merged" else 0) - (2 if draft else 0))
    robustness = clamp((6 if has_tests else 4) + (1 if doc_touch_ratio > 0.1 else 0))
    clean_code = clamp(7 - (size_penalty / 2))
    reusability = clamp(6 + (doc_touch_ratio * 2) - (changed_files / 50.0))
    ingenuity = clamp(5 + min(3.0, (doc_touch_ratio * 2)) - (size_penalty / 3.0))

    # Attention is 0-100
    risk = 0
    if churn > 600:
        risk += 30
    if not has_tests:
        risk += 20
    if draft:
        risk += 10
    if changed_files > 30:
        risk += 10
    if state == "open":
        risk += 15

    attention = max(0.0, min(100.0, 30.0 + risk - (doc_touch_ratio * 10.0)))

    return Scores(
        code_quality=code_quality,
        verbosity=verbosity,
        efficiency=efficiency,
        stability=stability,
        robustness=robustness,
        clean_code=clean_code,
        reusability=reusability,
        ingenuity=ingenuity,
        attention=attention,
    )


def scores_to_dict(scores: Scores) -> dict:
    return {
        "code_quality": scores.code_quality,
        "verbosity": scores.verbosity,
        "efficiency": scores.efficiency,
        "stability": scores.stability,
        "robustness": scores.robustness,
        "clean_code": scores.clean_code,
        "reusability": scores.reusability,
        "ingenuity": scores.ingenuity,
        "attention": scores.attention,
    }