import Database from 'better-sqlite3';
import { RunRow } from './types.js';

export function openDb(path: string) {
  const db = new Database(path);
  db.pragma('journal_mode = WAL');
  db.exec(`
    CREATE TABLE IF NOT EXISTS runs (
      id TEXT PRIMARY KEY,
      title TEXT,prompt TEXT,status TEXT,repo TEXT,branch TEXT,
      created_at TEXT,updated_at TEXT,duration_seconds INTEGER,
      pr_url TEXT,details_url TEXT,raw JSON
    );
  `);
  return db;
}

export function upsertRun(db: Database.Database, row: RunRow) {
  const stmt = db.prepare(`INSERT INTO runs (
    id,title,prompt,status,repo,branch,created_at,updated_at,duration_seconds,pr_url,details_url,raw
  ) VALUES (@id,@title,@prompt,@status,@repo,@branch,@created_at,@updated_at,@duration_seconds,@pr_url,@details_url,@raw)
  ON CONFLICT(id) DO UPDATE SET
    title=excluded.title,prompt=excluded.prompt,status=excluded.status,repo=excluded.repo,branch=excluded.branch,
    created_at=excluded.created_at,updated_at=excluded.updated_at,duration_seconds=excluded.duration_seconds,
    pr_url=excluded.pr_url,details_url=excluded.details_url,raw=excluded.raw`);
  stmt.run({ ...row, raw: JSON.stringify(row.raw ?? null) });
}