import os
import asyncio
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from .db import open_db, ensure_schema, get_recent_prs, get_recent_runs_with_pr_urls, upsert_pr, link_run_pr
from .github import parse_pr_url, enrich_pr
from .scoring import compute_attention
from .recommend import generate_roadmap_hint

load_dotenv()

app = FastAPI(title="Cursor Agents Review Server")


class ReviewPRsRequest(BaseModel):
    limit: int = 20
    repo: Optional[str] = None  # owner/repo filter (optional)


def _row_to_dict(row) -> Dict[str, Any]:
    return {
        key: row[key]
        for key in row.keys()
    }


async def _enrich_from_runs_if_needed(limit: int) -> None:
    conn = open_db()
    ensure_schema(conn)
    existing = get_recent_prs(conn, limit=limit)
    if existing:
        conn.close()
        return

    runs = get_recent_runs_with_pr_urls(conn, limit=limit)
    seen_ids = set()
    for r in runs:
        pr_url = r["pr_url"]
        parsed = parse_pr_url(pr_url)
        if not parsed:
            continue
        owner, repo, number = parsed
        pr_id = f"{owner}/{repo}#{number}"
        if pr_id in seen_ids:
            continue
        seen_ids.add(pr_id)
        data = await enrich_pr(owner, repo, number)
        try:
            upsert_pr(conn, data)
            link_run_pr(conn, r["id"], data["id"])
        except Exception:
            # continue gracefully on write errors
            pass

    conn.close()


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/tools/review_prs")
async def review_prs(body: ReviewPRsRequest) -> JSONResponse:
    limit = max(1, min(100, body.limit or 20))

    await _enrich_from_runs_if_needed(limit)

    conn = open_db()
    ensure_schema(conn)
    rows = get_recent_prs(conn, limit=limit)

    # Optional filter by repo
    if body.repo:
        filtered = [row for row in rows if f"{row['owner']}/{row['repo']}" == body.repo]
    else:
        filtered = rows

    items: List[Dict[str, Any]] = []
    for row in filtered:
        pr = _row_to_dict(row)
        score, factors = compute_attention(pr)
        pr["attention"] = {"score": score, "factors": factors}
        # Normalize types for stable JSON shape
        pr["draft"] = bool(pr.get("draft"))
        pr["has_tests"] = bool(pr.get("has_tests"))
        pr["review_count"] = int(pr.get("review_count") or 0)
        pr["doc_touch_ratio"] = float(pr.get("doc_touch_ratio") or 0.0)
        items.append(pr)

    items.sort(key=lambda x: x["attention"]["score"], reverse=True)

    roadmap_hint = generate_roadmap_hint(items)

    response = {"ranked": items, "roadmap_hint": roadmap_hint}
    return JSONResponse(response)


# Local run helper
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server.main:app", host="127.0.0.1", port=int(os.environ.get("PORT", 7399)), reload=False)