import os
import sqlite3
from typing import Any, Dict, List, Optional

DB_PATH = os.getenv("DB_PATH", os.path.abspath(os.path.join(os.path.dirname(__file__), "../cursor_agents.db")))


_SCHEMA_ENSURED = False

def _ensure_schema(conn: sqlite3.Connection) -> None:
    global _SCHEMA_ENSURED
    if _SCHEMA_ENSURED:
        return
    conn.executescript(
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
        """
    )
    _SCHEMA_ENSURED = True


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


def list_runs(limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, title, prompt, status, repo, branch, created_at, updated_at,
                   duration_seconds, pr_url, details_url, raw
            FROM runs
            ORDER BY (updated_at IS NULL), updated_at DESC, (created_at IS NULL), created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        rows = cur.fetchall()
        results: List[Dict[str, Any]] = []
        for r in rows:
            item = dict(r)
            # raw may be JSON text depending on writer, try to keep as-is string or parse best-effort
            results.append(item)
        return results


def get_run(run_id: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, title, prompt, status, repo, branch, created_at, updated_at,
                   duration_seconds, pr_url, details_url, raw
            FROM runs WHERE id = ?
            """,
            (run_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None