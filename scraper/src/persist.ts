import Database from 'better-sqlite3';
import { RunRow } from './types.js';
import { existsSync, readFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';

function applySchemaIfPresent(db: Database.Database) {
  const explicitPath = process.env.SCHEMA_SQL_PATH;
  const candidatePaths = [
    explicitPath,
    // common default locations
    resolve(process.cwd(), '../shared/schema.sql'),
    resolve(process.cwd(), 'shared/schema.sql'),
  ].filter(Boolean) as string[];

  for (const filePath of candidatePaths) {
    if (existsSync(filePath)) {
      const sql = readFileSync(filePath, 'utf8');
      const txn = db.transaction(() => {
        db.exec(sql);
      });
      txn();
      return; // applied
    }
  }
}

export function openDb(path: string) {
  // Ensure directory exists for the DB file
  try {
    mkdirSync(dirname(resolve(path)), { recursive: true });
  } catch {}

  const db = new Database(path);
  db.pragma('journal_mode = WAL');
  db.pragma('foreign_keys = ON');
  db.pragma('busy_timeout = 5000');

  // Optionally apply shared schema if available
  try {
    applySchemaIfPresent(db);
  } catch (err) {
    // Non-fatal: continue with local fallback table creation
  }

  // Fallback: ensure the required table exists for the scraper to function
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

// Cache detected columns for the runs table per DB instance
const dbToRunsColumns = new WeakMap<Database.Database, Set<string>>();

function getRunsColumns(db: Database.Database): Set<string> {
  let cols = dbToRunsColumns.get(db);
  if (cols) return cols;
  const rows = db.prepare("PRAGMA table_info('runs')").all() as Array<{ name: string }>;
  cols = new Set(rows.map(r => r.name));
  dbToRunsColumns.set(db, cols);
  return cols;
}

export function upsertRun(db: Database.Database, row: RunRow) {
  const available = getRunsColumns(db);

  // Filter to only columns that exist in the table
  const entries = Object.entries(row).filter(([key, value]) => {
    if (key === 'raw' && !available.has('raw')) return false;
    return available.has(key);
  });
  if (!entries.some(([k]) => k === 'id')) {
    throw new Error("runs table must contain an 'id' column");
  }

  // Serialize raw if present
  const values: Record<string, unknown> = {};
  for (const [k, v] of entries) {
    values[k] = k === 'raw' ? JSON.stringify((v as any) ?? null) : v;
  }

  const columns = entries.map(([k]) => k);
  const placeholders = columns.map(c => `@${c}`);
  const updateAssignments = columns
    .filter(c => c !== 'id')
    .map(c => `${c}=excluded.${c}`);

  const sql = `INSERT INTO runs (${columns.join(',')}) VALUES (${placeholders.join(',')})\n` +
    `ON CONFLICT(id) DO UPDATE SET ${updateAssignments.join(',')}`;

  const stmt = db.prepare(sql);
  stmt.run(values);
}