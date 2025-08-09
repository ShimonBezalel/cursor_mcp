import os
import re
import json
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse
from datetime import date, datetime
from decimal import Decimal

import httpx

__all__ = [
    "parse_pr_identifier",
    "parse_pr_url",
    "safe_json_dumps",
    "enrich_pr",
]


_GITHUB_API_VERSION = "2022-11-28"


def parse_pr_identifier(identifier: str) -> Tuple[str, str, int]:
    """Parse a GitHub PR identifier from various formats.

    Supported formats:
    - Full web URL: https://github.com/{owner}/{repo}/pull/{number}[/*]
    - API URL: https://api.github.com/repos/{owner}/{repo}/pulls/{number}
    - Short form: {owner}/{repo}#{number}

    Returns a tuple of (owner, repo, pr_number).
    Raises ValueError if parsing fails.
    """
    identifier = identifier.strip()

    # Short form: owner/repo#123
    short_match = re.match(r"^(?P<owner>[^\s/]+)/(?P<repo>[^\s#]+)#(?P<number>\d+)$", identifier)
    if short_match:
        owner = short_match.group("owner")
        repo = short_match.group("repo")
        number = int(short_match.group("number"))
        return owner, repo, number

    # URL forms
    parsed = urlparse(identifier)
    if parsed.scheme and parsed.netloc:
        host = parsed.netloc.lower()
        path = parsed.path.strip("/")
        segments = [seg for seg in path.split("/") if seg]

        # https://github.com/{owner}/{repo}/pull/{number}[/*]
        if host.endswith("github.com") and len(segments) >= 4 and segments[2] == "pull":
            owner = segments[0]
            repo = segments[1]
            try:
                number = int(segments[3])
            except ValueError as exc:
                raise ValueError(f"Invalid PR number in URL: {identifier}") from exc
            return owner, repo, number

        # https://api.github.com/repos/{owner}/{repo}/pulls/{number}
        if host == "api.github.com" and len(segments) >= 5:
            # expected: repos/{owner}/{repo}/pulls/{number}
            if segments[0] == "repos" and segments[3] in ("pulls", "pull"):
                owner = segments[1]
                repo = segments[2]
                try:
                    number = int(segments[4])
                except (IndexError, ValueError) as exc:
                    raise ValueError(f"Invalid PR number in API URL: {identifier}") from exc
                return owner, repo, number

    raise ValueError(f"Unable to parse PR identifier: {identifier}")


def parse_pr_url(url: str) -> Tuple[str, str, int]:
    """Backward-compatible alias for parse_pr_identifier for URL inputs."""
    return parse_pr_identifier(url)


def _json_default_fallback(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, set):
        return list(value)
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except Exception:
            return value.decode("utf-8", errors="replace")
    if isinstance(value, Decimal):
        return float(value)
    # Last resort stringification to avoid serialization errors
    return str(value)


def safe_json_dumps(obj: Any) -> str:
    """Dump an object to JSON safely.

    - Uses UTF-8 without escaping non-ASCII
    - Disallows NaN/Infinity
    - Coerces common non-serializable types
    """
    return json.dumps(
        obj,
        ensure_ascii=False,
        allow_nan=False,
        default=_json_default_fallback,
        separators=(",", ":"),
    )


async def enrich_pr(pr_identifier: str, github_token: Optional[str] = None, *, client: Optional[httpx.AsyncClient] = None) -> Dict[str, Any]:
    """Fetch a PR from GitHub and upsert it into the database.

    Args:
        pr_identifier: PR URL or short id (e.g., "owner/repo#123").
        github_token: GitHub token; if None, will read from env GITHUB_TOKEN.
        client: Optional shared httpx.AsyncClient to reuse.

    Returns:
        A dictionary representing the normalized PR record, suitable for storage.

    Raises:
        ValueError: If the PR identifier cannot be parsed or token is missing.
        httpx.HTTPError: If the GitHub request fails.
    """
    owner, repo, number = parse_pr_identifier(pr_identifier)

    token = github_token or os.getenv("GITHUB_TOKEN")
    if not token:
        raise ValueError("GITHUB_TOKEN is required")

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": _GITHUB_API_VERSION,
        "User-Agent": "github-enrichment-module/1.0",
    }

    close_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=30.0)
        close_client = True

    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}"

    try:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        pr = response.json()

        # Normalize the PR record for storage
        normalized: Dict[str, Any] = {
            "owner": owner,
            "repo": repo,
            "number": number,
            "url": pr.get("html_url"),
            "title": pr.get("title"),
            "state": pr.get("state"),
            "draft": pr.get("draft"),
            "merged": pr.get("merged"),
            "user_login": (pr.get("user") or {}).get("login"),
            "labels": [lbl.get("name") for lbl in pr.get("labels", []) if isinstance(lbl, dict)],
            "assignees": [asg.get("login") for asg in pr.get("assignees", []) if isinstance(asg, dict)],
            "requested_reviewers": [rv.get("login") for rv in pr.get("requested_reviewers", []) if isinstance(rv, dict)],
            "base_ref": (pr.get("base") or {}).get("ref"),
            "head_ref": (pr.get("head") or {}).get("ref"),
            "additions": pr.get("additions"),
            "deletions": pr.get("deletions"),
            "changed_files": pr.get("changed_files"),
            "created_at": pr.get("created_at"),
            "updated_at": pr.get("updated_at"),
            "closed_at": pr.get("closed_at"),
            "raw": pr,
        }

        # Try to upsert into DB; support both sync and async implementations
        try:
            from server.db import upsert_pr as _upsert_pr  # type: ignore
        except Exception as import_exc:
            raise ImportError(
                "Could not import upsert_pr from server.db. Ensure the DB utility is available as server.db.upsert_pr."
            ) from import_exc

        result_or_coro = _upsert_pr(normalized)  # type: ignore
        # If the DB utility is async, await the returned awaitable. Otherwise, proceed.
        try:
            import inspect  # local import to avoid top-level dependency if not needed
            if inspect.isawaitable(result_or_coro):
                await result_or_coro  # type: ignore
        except Exception:
            # If inspect or awaiting fails for unexpected reasons, re-raise to surface DB contract issues
            raise

        return normalized
    finally:
        if close_client:
            await client.aclose()