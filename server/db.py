import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = os.getenv("DB_PATH", str(Path(__file__).resolve().parent.parent / "cursor_agents.db"))


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS runs (
          id TEXT PRIMARY KEY,
          title TEXT,prompt TEXT,status TEXT,repo TEXT,branch TEXT,
          created_at TEXT,updated_at TEXT,duration_seconds INTEGER,
          pr_url TEXT,details_url TEXT,raw JSON
        );
        """
    )


def _connect() -> sqlite3.Connection:
    # row_factory to dict-like rows
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


def get_runs(limit: int = 25) -> List[Dict[str, Any]]:
    with _connect() as conn:
        # Order by updated_at desc if present, else created_at, else id
        rows = conn.execute(
            """
            SELECT id, title, prompt, status, repo, branch,
                   created_at, updated_at, duration_seconds,
                   pr_url, details_url
            FROM runs
            ORDER BY COALESCE(updated_at, created_at, id) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_run_by_id(run_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, title, prompt, status, repo, branch,
                   created_at, updated_at, duration_seconds,
                   pr_url, details_url
            FROM runs WHERE id = ?
            """,
            (run_id,),
        ).fetchone()
        return dict(row) if row else None


def get_recent_prs(limit: int = 20) -> List[Dict[str, Any]]:
    # Derive from runs table: distinct non-null PR URLs
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT pr_url AS url,
                   MAX(COALESCE(updated_at, created_at)) AS last_seen_at,
                   COUNT(*) AS occurrences,
                   MAX(title) AS sample_title
            FROM runs
            WHERE pr_url IS NOT NULL AND TRIM(pr_url) <> ''
            GROUP BY pr_url
            ORDER BY last_seen_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]