import os
import sqlite3
from typing import Any, Dict, Iterable, List, Optional, Tuple


DEFAULT_DB_PATH = os.environ.get("DB_PATH", "/workspace/cursor_agents.db")


def open_db(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = db_path or DEFAULT_DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    # Runs table (created by the scraper); ensure exists with expected columns
    cur.execute(
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
          raw JSON
        );
        """
    )

    # PRs enriched locally
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS prs (
          id TEXT PRIMARY KEY,
          owner TEXT,
          repo TEXT,
          number INTEGER,
          title TEXT,
          author TEXT,
          state TEXT,
          html_url TEXT,
          created_at TEXT,
          updated_at TEXT,
          merged_at TEXT,
          additions INTEGER,
          deletions INTEGER,
          changed_files INTEGER,
          draft INTEGER,
          review_count INTEGER,
          ci_status TEXT,
          has_tests INTEGER,
          doc_touch_ratio REAL,
          diff_stats JSON
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS run_prs (
          run_id TEXT,
          pr_id TEXT,
          PRIMARY KEY (run_id, pr_id)
        );
        """
    )

    conn.commit()


def get_recent_prs(conn: sqlite3.Connection, limit: int = 20) -> List[sqlite3.Row]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT * FROM prs
        ORDER BY datetime(COALESCE(updated_at, created_at)) DESC
        LIMIT ?
        """,
        (limit,),
    )
    return cur.fetchall()


def get_recent_runs_with_pr_urls(conn: sqlite3.Connection, limit: int = 50) -> List[sqlite3.Row]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT * FROM runs
        WHERE pr_url IS NOT NULL AND TRIM(pr_url) <> ''
        ORDER BY datetime(COALESCE(updated_at, created_at)) DESC
        LIMIT ?
        """,
        (limit,),
    )
    return cur.fetchall()


def upsert_pr(conn: sqlite3.Connection, pr: Dict[str, Any]) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO prs (
          id, owner, repo, number, title, author, state, html_url,
          created_at, updated_at, merged_at, additions, deletions, changed_files,
          draft, review_count, ci_status, has_tests, doc_touch_ratio, diff_stats
        ) VALUES (
          :id, :owner, :repo, :number, :title, :author, :state, :html_url,
          :created_at, :updated_at, :merged_at, :additions, :deletions, :changed_files,
          :draft, :review_count, :ci_status, :has_tests, :doc_touch_ratio, :diff_stats
        )
        ON CONFLICT(id) DO UPDATE SET
          title=excluded.title,
          author=excluded.author,
          state=excluded.state,
          html_url=excluded.html_url,
          created_at=excluded.created_at,
          updated_at=excluded.updated_at,
          merged_at=excluded.merged_at,
          additions=excluded.additions,
          deletions=excluded.deletions,
          changed_files=excluded.changed_files,
          draft=excluded.draft,
          review_count=excluded.review_count,
          ci_status=excluded.ci_status,
          has_tests=excluded.has_tests,
          doc_touch_ratio=excluded.doc_touch_ratio,
          diff_stats=excluded.diff_stats
        ;
        """,
        {**pr, "diff_stats": pr.get("diff_stats")},
    )
    conn.commit()


def link_run_pr(conn: sqlite3.Connection, run_id: str, pr_id: str) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR IGNORE INTO run_prs (run_id, pr_id) VALUES (?, ?)
        """,
        (run_id, pr_id),
    )
    conn.commit()