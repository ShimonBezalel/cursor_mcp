-- shared/schema.sql
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
CREATE INDEX IF NOT EXISTS runs_updated ON runs(updated_at DESC);

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
  diff_stats JSON                   -- raw enrichment cache
);
CREATE INDEX IF NOT EXISTS prs_updated ON prs(updated_at DESC);

CREATE TABLE IF NOT EXISTS run_prs (
  run_id TEXT,
  pr_id TEXT,
  PRIMARY KEY (run_id, pr_id)
);