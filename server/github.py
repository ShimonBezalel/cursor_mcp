import os
import re
from typing import Any, Dict, Optional, Tuple, List
import httpx

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_API = "https://api.github.com"


def parse_pr_url(pr_url: str) -> Optional[Tuple[str, str, int]]:
    # Accept forms like https://github.com/owner/repo/pull/123
    m = re.match(r"https?://github.com/([^/]+)/([^/]+)/pull/(\d+)", pr_url)
    if not m:
        return None
    owner, repo, number = m.group(1), m.group(2), int(m.group(3))
    return owner, repo, number


async def fetch_json(client: httpx.AsyncClient, url: str) -> Optional[Dict[str, Any]]:
    try:
        r = await client.get(url, timeout=20)
        if r.status_code >= 400:
            return None
        return r.json()
    except Exception:
        return None


async def enrich_pr(owner: str, repo: str, number: int) -> Dict[str, Any]:
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    async with httpx.AsyncClient(base_url=GITHUB_API, headers=headers) as client:
        pr = await fetch_json(client, f"/repos/{owner}/{repo}/pulls/{number}")
        files = await fetch_json(client, f"/repos/{owner}/{repo}/pulls/{number}/files") or []
        reviews = await fetch_json(client, f"/repos/{owner}/{repo}/pulls/{number}/reviews") or []

    review_count = len(reviews) if isinstance(reviews, list) else 0

    additions = pr.get("additions") if pr else None
    deletions = pr.get("deletions") if pr else None
    changed_files = pr.get("changed_files") if pr else None

    # Heuristics from changed files
    has_tests = False
    doc_touches = 0
    file_count = 0
    if isinstance(files, list):
        for f in files:
            filename = f.get("filename", "")
            file_count += 1
            lower = filename.lower()
            if any(part in lower for part in ["test/", "/test/", "tests/", ".spec.", ".test."]):
                has_tests = True or has_tests
            if any(part in lower for part in ["readme", "docs/", "/docs/", ".md", ".rst"]):
                doc_touches += 1
    doc_touch_ratio = (doc_touches / file_count) if file_count else 0.0

    data = {
        "id": f"{owner}/{repo}#{number}",
        "owner": owner,
        "repo": repo,
        "number": number,
        "title": (pr or {}).get("title"),
        "author": ((pr or {}).get("user") or {}).get("login"),
        "state": (pr or {}).get("state"),
        "html_url": (pr or {}).get("html_url") or f"https://github.com/{owner}/{repo}/pull/{number}",
        "created_at": (pr or {}).get("created_at"),
        "updated_at": (pr or {}).get("updated_at"),
        "merged_at": (pr or {}).get("merged_at"),
        "additions": additions,
        "deletions": deletions,
        "changed_files": changed_files,
        "draft": 1 if (pr or {}).get("draft") else 0,
        "review_count": review_count,
        "ci_status": "unknown",  # can be enhanced later
        "has_tests": 1 if has_tests else 0,
        "doc_touch_ratio": float(doc_touch_ratio),
        "diff_stats": None,
    }
    return data