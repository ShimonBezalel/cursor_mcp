import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

_DB_PATH_CACHE: Optional[str] = None


def _resolve_db_path() -> str:
    global _DB_PATH_CACHE
    if _DB_PATH_CACHE is not None:
        return _DB_PATH_CACHE

    # Try shared config first (optional dependency)
    db_path: Optional[str] = None
    try:
        # Lazily import in case shared config is not present yet
        from shared.config import DB_PATH as SHARED_DB_PATH  # type: ignore

        if isinstance(SHARED_DB_PATH, str) and SHARED_DB_PATH.strip():
            db_path = SHARED_DB_PATH.strip()
    except Exception:
        # Best-effort import; ignore if not available
        db_path = None

    # Environment overrides
    db_path = os.environ.get("DB_PATH", db_path)
    db_path = os.environ.get("DATABASE_PATH", db_path)

    # Default location if still unspecified
    if not db_path:
        default_dir = Path("/workspace/data")
        default_dir.mkdir(parents=True, exist_ok=True)
        db_path = str(default_dir / "app.sqlite3")

    # Normalize sqlite URL if provided (sqlite:///abs/path or file:/path)
    if "://" in db_path:
        if db_path.startswith("sqlite:///"):
            db_path = db_path.replace("sqlite:///", "/", 1)
        elif db_path.startswith("file:"):
            # sqlite file URI; strip scheme for on-disk path if no query params
            db_path = db_path.replace("file:", "", 1)

    # Ensure parent directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    _DB_PATH_CACHE = db_path
    return db_path


def _read_schema_sql() -> Optional[str]:
    # Prefer absolute path in workspace
    candidate_paths: Iterable[Path] = [
        Path("/workspace/shared/schema.sql"),
        Path(__file__).resolve().parent.parent / "shared" / "schema.sql",
        Path(__file__).resolve().parent / "shared" / "schema.sql",
    ]
    for path in candidate_paths:
        try:
            if path.exists() and path.is_file():
                return path.read_text(encoding="utf-8")
        except Exception:
            continue
    return None


def _ensure_minimal_schema(conn_obj: sqlite3.Connection) -> None:
    # Create minimal tables if schema.sql is not available
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
            id TEXT PRIMARY KEY,
            number INTEGER,
            repo TEXT,
            title TEXT,
            body TEXT,
            state TEXT,
            url TEXT,
            author TEXT,
            created_at TEXT,
            updated_at TEXT,
            raw TEXT,
            UNIQUE(number, repo)
        );
        """
    )


def _table_exists(conn_obj: sqlite3.Connection, table_name: str) -> bool:
    cur = conn_obj.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table_name,),
    )
    return cur.fetchone() is not None


def _ensure_schema(conn_obj: sqlite3.Connection) -> None:
    # Quick check to avoid re-running schema if both core tables exist
    if _table_exists(conn_obj, "runs") and _table_exists(conn_obj, "prs"):
        return

    # Try shared/schema.sql first
    schema = _read_schema_sql()
    if schema:
        conn_obj.executescript(schema)
    else:
        _ensure_minimal_schema(conn_obj)

    conn_obj.commit()


def conn() -> sqlite3.Connection:
    db_path = _resolve_db_path()
    connection = sqlite3.connect(db_path)
    # Row factory returns sqlite3.Row to allow dict conversion
    connection.row_factory = sqlite3.Row

    # Pragmas for reliability
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


def _rows_to_dicts(rows: Iterable[sqlite3.Row]) -> List[Dict[str, Any]]:
    return [dict(row) for row in rows]


def get_runs(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    with conn() as c:
        if limit is not None:
            cur = c.execute(
                """
                SELECT *
                FROM runs
                ORDER BY COALESCE(updated_at, created_at) DESC
                LIMIT ?
                """,
                (int(limit),),
            )
        else:
            cur = c.execute(
                """
                SELECT *
                FROM runs
                ORDER BY COALESCE(updated_at, created_at) DESC
                """
            )
        return _rows_to_dicts(cur.fetchall())


def get_recent_prs(limit: Optional[int] = 50) -> List[Dict[str, Any]]:
    with conn() as c:
        if limit is not None:
            cur = c.execute(
                """
                SELECT *
                FROM prs
                ORDER BY COALESCE(updated_at, created_at) DESC
                LIMIT ?
                """,
                (int(limit),),
            )
        else:
            cur = c.execute(
                """
                SELECT *
                FROM prs
                ORDER BY COALESCE(updated_at, created_at) DESC
                """
            )
        return _rows_to_dicts(cur.fetchall())


def upsert_pr(pr_row: Mapping[str, Any]) -> None:
    # Normalize primary key
    pr_id = pr_row.get("id")
    repo = pr_row.get("repo")
    number = pr_row.get("number")

    if not pr_id:
        if repo is not None and number is not None:
            pr_id = f"{repo}#{number}"
        else:
            raise ValueError("upsert_pr requires 'id' or both 'repo' and 'number'")

    payload: Dict[str, Any] = {
        "id": str(pr_id),
        "number": int(number) if number is not None else None,
        "repo": str(repo) if repo is not None else None,
        "title": pr_row.get("title"),
        "body": pr_row.get("body"),
        "state": pr_row.get("state"),
        "url": pr_row.get("url"),
        "author": pr_row.get("author"),
        "created_at": pr_row.get("created_at"),
        "updated_at": pr_row.get("updated_at"),
        # Store the raw dict as JSON string if provided
        "raw": None,
    }

    raw_value = pr_row.get("raw")
    if raw_value is not None:
        try:
            import json

            payload["raw"] = json.dumps(raw_value)
        except Exception:
            # Fallback to string representation
            payload["raw"] = str(raw_value)

    with conn() as c:
        c.execute(
            """
            INSERT INTO prs (
                id, number, repo, title, body, state, url, author, created_at, updated_at, raw
            ) VALUES (
                :id, :number, :repo, :title, :body, :state, :url, :author, :created_at, :updated_at, :raw
            )
            ON CONFLICT(id) DO UPDATE SET
                number=excluded.number,
                repo=excluded.repo,
                title=excluded.title,
                body=excluded.body,
                state=excluded.state,
                url=excluded.url,
                author=excluded.author,
                created_at=excluded.created_at,
                updated_at=excluded.updated_at,
                raw=excluded.raw
            """,
            payload,
        )
        c.commit()