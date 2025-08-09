from typing import Any, Dict, List


def generate_roadmap_hint(ranked: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not ranked:
        return {
            "text": "No PRs found. Scrape recent runs or add PR URLs to runs.pr_url to bootstrap.",
            "rationale": "The database has no enriched PRs yet.",
            "next_actions": [
                "Run the scraper to populate recent agent runs",
                "Ensure runs have pr_url populated",
                "Re-run review_prs to enrich and rank"
            ],
        }

    top = ranked[0]
    insights = []
    if top.get("attention", {}).get("factors", {}).get("ci_status") in {"failure", "error"}:
        insights.append("Top PR has failing CI; prioritize stabilizing pipeline and fixing tests.")
    if (top.get("attention", {}).get("factors", {}).get("churn_lines") or 0) > 800:
        insights.append("High churn detected; request a focused split into smaller PRs.")
    if not top.get("has_tests"):
        insights.append("Tests missing; ask for unit/integration tests covering critical paths.")
    if not insights:
        insights.append("Start with the highest attention PR; review scope, tests, and CI status.")

    return {
        "text": insights[0],
        "rationale": "Derived from top-ranked PR attention factors.",
        "next_actions": [
            "Assign a reviewer to the top 1-3 PRs",
            "Ensure CI passes and tests are present",
            "Document any breaking changes"
        ],
    }