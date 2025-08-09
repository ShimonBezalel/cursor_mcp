from __future__ import annotations

from typing import Any, Dict, List, Protocol, Sequence

try:
    # Prefer the real Scores class from scoring heuristics if present
    from .scoring import Scores  # type: ignore
except Exception:
    # Fallback protocol so this module works even if scoring.py is not present
    class Scores(Protocol):  # type: ignore
        code_quality: float
        verbosity: float
        efficiency: float
        stability: float
        robustness: float
        clean_code: float
        reusability: float
        ingenuity: float
        attention: float


NEXT_STEPS_TEMPLATES: Dict[str, str] = {
    'tests_missing': "Add/extend unit tests targeting new logic and edge cases; gate with CI.",
    'docs_low': "Augment README/inline docs; explain rationale and trade-offs.",
    'too_large': "Split PR into cohesive commits/modules; isolate refactors from logic changes.",
    'needs_review': "Request review from owner of touched module; add checklists.",
    'perf_risk': "Benchmark hotspots; add micro-bench or profiling notes.",
}


def recommendations(scores: Scores, pr: Dict[str, Any]) -> List[str]:
    """Return up to 3 actionable next-step recommendations for a PR.

    Args:
        scores: Heuristic scores for the PR (0–10 per dimension; attention 0–100).
        pr:     PR metadata dict with optional keys like 'has_tests'.

    Returns:
        A list of up to three short, actionable recommendation strings.
    """
    recs: List[str] = []

    has_tests = bool(pr.get('has_tests'))

    if getattr(scores, 'stability', 0.0) < 6.0 or not has_tests:
        recs.append(NEXT_STEPS_TEMPLATES['tests_missing'])
    if getattr(scores, 'verbosity', 0.0) < 5.0:
        recs.append(NEXT_STEPS_TEMPLATES['docs_low'])
    if getattr(scores, 'clean_code', 0.0) < 6.0:
        recs.append(NEXT_STEPS_TEMPLATES['too_large'])
    if getattr(scores, 'attention', 0.0) > 60.0:
        recs.append(NEXT_STEPS_TEMPLATES['needs_review'])
    if getattr(scores, 'efficiency', 0.0) < 5.0:
        recs.append(NEXT_STEPS_TEMPLATES['perf_risk'])

    # De-duplicate while preserving order, and cap at 3
    seen = set()
    deduped: List[str] = []
    for r in recs:
        if r not in seen:
            seen.add(r)
            deduped.append(r)
            if len(deduped) >= 3:
                break

    return deduped


def roadmap_hint(aggregate: Sequence[Dict[str, Any]]) -> str:
    """Produce a lightweight roadmap nudge from a batch of scored PRs.

    Args:
        aggregate: Sequence of items like {'scores': Scores, 'pr': dict}.

    Returns:
        A single short hint string.
    """
    if not aggregate:
        return "No data yet."

    total = len(aggregate)

    attn_high = sum(
        1 for a in aggregate
        if a.get('scores') is not None and float(getattr(a['scores'], 'attention', 0.0)) > 70.0
    )
    low_docs = sum(
        1 for a in aggregate
        if a.get('scores') is not None and float(getattr(a['scores'], 'verbosity', 0.0)) < 5.0
    )
    low_tests = sum(
        1 for a in aggregate
        if a.get('pr') is not None and not bool(a['pr'].get('has_tests'))
    )
    perf_risk = sum(
        1 for a in aggregate
        if a.get('scores') is not None and float(getattr(a['scores'], 'efficiency', 0.0)) < 5.0
    )

    if attn_high >= max(2, total // 3) and low_docs >= max(2, total // 4):
        return "Prioritize a documentation and testing sprint; enforce PR size guardrails and module ownership."
    if attn_high >= max(2, total // 3):
        return "Enforce PR size guardrails; require risk checklists on high-attention changes."
    if low_docs >= max(2, total // 4):
        return "Invest in better documentation and rationale sections in PRs; adopt a docs checklist."
    if low_tests >= max(2, total // 4):
        return "Schedule a testing push; add CI gates requiring targeted unit tests on changed modules."
    if perf_risk >= max(2, total // 4):
        return "Add performance budgets and basic benchmarks for hotspots; profile critical paths."

    return "Steady state; continue current review process and incremental improvements."