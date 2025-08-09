# server/db.py
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

# ---------- DB path resolution (env > shared.config > sane default) ----------
_DB_PATH_CACHE: Optional[str] = None

def _resolve_db_path() -> str:
    global _DB_PATH_CACHE
    if _DB_PATH_CACHE is not None:
        return _DB_PATH_CACHE

    db_path: Optional[str] = None

    # Try shared config (optional dependency)
    try:
        from shared.config import DB_PATH as SHARED_DB_PATH  # type: ignore
        if isinstance(SHARED_DB_PATH, str) and SHARED_DB_PATH.strip():
            db_path = SHARED_DB_PATH.strip()
    except Exception:
        pass

    # Environment overrides
    db_path = os.environ.get("DB_PATH", db_path)
    db_path = os.environ.get("DATABASE_PATH", db_path)

    # Default location if still unspecified
    if not db_path:
        default_dir = Path("/workspace/data")
        default_dir.mkdir(parents=True, exist_ok=True)
        db_path = str(default_dir / "cursor_agents.db")

    # Normalize sqlite URL forms (sqlite:///abs/path or file:/path)
    if "://" in db_path:
        if db_path.startswith("sqlite:///"):
            db_path = db_path.replace("sqlite:///", "/", 1)
        elif db_path.startswith("file:"):
            # Strip scheme if simple file-URI
            db_path = db_path.replace("file:", "", 1)

    # Ensure parent exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    _DB_PATH_CACHE = db_path
    return db_path

# ---------- Schema bootstrap ----------
def _read_schema_sql() -> Optional[str]:
    candidates: Iterable[Path] = [
        Path("/workspace/shared/schema.sql"),
        Path(__file__).resolve().parent.parent / "shared" / "schema.sql",
        Path(__file__).resolve().parent / "shared" / "schema.sql",
    ]
    for p in candidates:
        try:
            if p.exists() and p.is_file():
                return p.read_text(encoding="utf-8")
        except Exception:
            continue
    return None

def _table_exists(conn_obj: sqlite3.Connection, table_name: str) -> bool:
    cur = conn_obj.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table_name,),
    )
    return cur.fetchone() is not None

def _ensure_minimal_schema(conn_obj: sqlite3.Connection) -> None:
    # Minimal but compatible with README schema (runs, prs, run_prs)
    conn_obj.executescript(
        """
        CREATE TABLE IF NOT EXISTS runs (
          id TEXT PRIMARY KEY,
          title TEXT,
          prompt TEXT,
          status TEXT,
          repo TEXT,
          branch TEXT,
          created_at TEXT,
          updated_at TEXT,
          duration_seconds INTEGER,
          pr_url TEXT,
          details_url TEXT,
          raw TEXT
        );

        CREATE TABLE IF NOT EXISTS prs (
          id TEXT PRIMARY KEY,              -- owner/repo#number
          owner TEXT,
          repo TEXT,
          number INTEGER,
          title TEXT,
          author TEXT,
          state TEXT,                       -- open/closed/merged
          html_url TEXT,
          created_at TEXT,
          updated_at TEXT,
          merged_at TEXT,
          additions INTEGER,
          deletions INTEGER,
          changed_files INTEGER,
          draft INTEGER,                    -- 0/1
          review_count INTEGER,
          ci_status TEXT,                   -- success/failure/pending/unknown
          has_tests INTEGER,                -- 0/1 heuristic
          doc_touch_ratio REAL,             -- 0..1
          diff_stats TEXT                   -- JSON cache
        );

        CREATE TABLE IF NOT EXISTS run_prs (
          run_id TEXT,
          pr_id TEXT,
          PRIMARY KEY (run_id, pr_id)
        );

        CREATE INDEX IF NOT EXISTS runs_updated ON runs (updated_at DESC);
        CREATE INDEX IF NOT EXISTS prs_updated  ON prs  (updated_at DESC);
        """
    )

def _ensure_schema(conn_obj: sqlite3.Connection) -> None:
    # Fast-path if both core tables exist
    if _table_exists(conn_obj, "runs") and _table_exists(conn_obj, "prs"):
        return

    schema = _read_schema_sql()
    if schema:
        conn_obj.executescript(schema)
    else:
        _ensure_minimal_schema(conn_obj)

    conn_obj.commit()

# ---------- Connection ----------
def conn() -> sqlite3.Connection:
    db_path = _resolve_db_path()
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row

    # Pragmas for durability + correctness
    try:
        connection.execute("PRAGMA journal_mode=WAL;")
    except Exception:
        pass
    try:
        connection.execute("PRAGMA foreign_keys=ON;")
    except Exception:
        pass

    _ensure_schema(connection)
    return connection

# ---------- Helpers ----------
def _rows_to_dicts(rows: Iterable[sqlite3.Row]) -> List[Dict[str, Any]]:
    return [dict(r) for r in rows]

# ---------- Queries ----------
def get_runs(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Return recent runs (most-recent first). If limit is None, return all.
    """
    q = """
        SELECT *
        FROM runs
        ORDER BY COALESCE(updated_at, created_at, id) DESC
    """
    args: Tuple[Any, ...] = ()
    if limit is not None:
        q += " LIMIT ?"
        args = (int(limit),)

    with conn() as c:
        cur = c.execute(q, args)
        return _rows_to_dicts(cur.fetchall())

def get_run_by_id(run_id: str) -> Optional[Dict[str, Any]]:
    with conn() as c:
        row = c.execute(
            """
            SELECT *
            FROM runs
            WHERE id = ?
            """,
            (run_id,),
        ).fetchone()
        return dict(row) if row else None

def get_recent_prs(limit: Optional[int] = 50) -> List[Dict[str, Any]]:
    """
    Prefer the canonical prs table. If it's empty, synthesize from runs.pr_url.
    """
    with conn() as c:
        # First try real PRs table
        prs = c.execute(
            """
            SELECT *
            FROM prs
            ORDER BY COALESCE(updated_at, created_at) DESC
            LIMIT ?
            """,
            (int(limit) if limit is not None else 50,),
        ).fetchall()
        if prs:
            return _rows_to_dicts(prs)

        # Fallback: derive distinct PR URLs from runs
        synth = c.execute(
            """
            SELECT pr_url AS html_url,
                   MAX(COALESCE(updated_at, created_at)) AS updated_at,
                   COUNT(*) AS occurrences,
                   MAX(title) AS title
            FROM runs
            WHERE pr_url IS NOT NULL AND TRIM(pr_url) <> ''
            GROUP BY pr_url
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (int(limit) if limit is not None else 50,),
        ).fetchall()
        # Normalize shape a bit
        out: List[Dict[str, Any]] = []
        for r in synth:
            d = dict(r)
            d["id"] = d.get("html_url", "")
            d["state"] = "open"  # unknown; placeholder
            out.append(d)
        return out

# ---------- Upserts ----------
def _normalize_pr_identity(pr_row: Mapping[str, Any]) -> Tuple[str, Optional[str], Optional[str], Optional[int]]:
    """
    Return (id, owner, repo, number).
    Accepts either explicit id 'owner/repo#number' or a GitHub URL.
    """
    pr_id = pr_row.get("id")
    owner = pr_row.get("owner")
    repo = pr_row.get("repo")
    number = pr_row.get("number")

    # Attempt to parse from URL if necessary
    if (owner is None or repo is None or number is None) and not pr_id:
        url = pr_row.get("html_url") or pr_row.get("url")
        if isinstance(url, str) and "github.com" in url and "/pull/" in url:
            try:
                parts = url.split("github.com/")[1].split("/pull/")
                org_repo = parts[0]
                num = int(parts[1].split("/")[0])
                owner, repo = org_repo.split("/", 1)
                number = num
            except Exception:
                pass

    if not pr_id and owner and repo and number is not None:
        pr_id = f"{owner}/{repo}#{int(number)}"

    if not pr_id:
        # Last resort: repo#number accepted (legacy)
        legacy_repo = pr_row.get("repo")
        if legacy_repo and number is not None:
            pr_id = f"{legacy_repo}#{int(number)}"

    if not pr_id:
        raise ValueError("upsert_pr requires 'id' or resolvable owner/repo/number (or a GitHub PR URL).")

    return str(pr_id), owner, repo, int(number) if number is not None else None

def upsert_pr(pr_row: Mapping[str, Any]) -> None:
    """
    Upsert into prs with normalized keys. Accepts flexible inputs:
      - keys from GitHub API (title, user.login, html_url, state, merged_at, additions, deletions, changed_files, draft, review_comments)
      - or simplified keys (url, author, repo, number, etc.)
    """
    import json

    pr_id, owner, repo, number = _normalize_pr_identity(pr_row)

    # Normalize fields
    title = pr_row.get("title")
    author = pr_row.get("author") or (pr_row.get("user") or {}).get("login")
    state = "merged" if pr_row.get("merged_at") else pr_row.get("state")
    html_url = pr_row.get("html_url") or pr_row.get("url")
    created_at = pr_row.get("created_at")
    updated_at = pr_row.get("updated_at")
    merged_at = pr_row.get("merged_at")
    additions = pr_row.get("additions") or 0
    deletions = pr_row.get("deletions") or 0
    changed_files = pr_row.get("changed_files") or pr_row.get("files_count") or 0
    draft = 1 if pr_row.get("draft") else 0
    review_count = pr_row.get("review_count") or pr_row.get("review_comments") or 0
    ci_status = pr_row.get("ci_status") or "unknown"
    has_tests = 1 if pr_row.get("has_tests") else 0
    doc_touch_ratio = float(pr_row.get("doc_touch_ratio") or 0.0)
    diff_stats = pr_row.get("diff_stats")
    if diff_stats is not None and not isinstance(diff_stats, str):
        try:
            diff_stats = json.dumps(diff_stats)
        except Exception:
            diff_stats = "{}"

    row = {
        "id": pr_id,
        "owner": owner,
        "repo": repo,
        "number": number,
        "title": title,
        "author": author,
        "state": state,
        "html_url": html_url,
        "created_at": created_at,
        "updated_at": updated_at,
        "merged_at": merged_at,
        "additions": int(additions or 0),
        "deletions": int(deletions or 0),
        "changed_files": int(changed_files or 0),
        "draft": int(draft or 0),
        "review_count": int(review_count or 0),
        "ci_status": ci_status,
        "has_tests": int(has_tests or 0),
        "doc_touch_ratio": float(doc_touch_ratio),
        "diff_stats": diff_stats,
    }

    with conn() as c:
        keys = ",".join(row.keys())
        qmarks = ",".join([f":{k}" for k in row.keys()])
        update = ",".join([f"{k}=excluded.{k}" for k in row.keys() if k != "id"])
        sql = f"INSERT INTO prs ({keys}) VALUES ({qmarks}) ON CONFLICT(id) DO UPDATE SET {update}"
        c.execute(sql, row)
        c.commit()
