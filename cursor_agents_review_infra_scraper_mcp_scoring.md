# Cursor Agents Review Infra

An opinionated, batteries‑included scaffold to:

- **Scrape Cursor Agent runs** from `cursor.com/agents` (no Slack required)
- **Harvest PRs** created by agents/background workers
- **Rank PRs** on: code quality, verbosity, efficiency, stability, robustness, clean code, reusability, ingenuity, and **need for human attention**
- **Expose MCP tools** so you can ask Cursor (or any MCP client):
  - `list_tasks`, `task`, `summarize_recent`
  - `review_prs` → returns ranked PRs with next‑step recommendations

Works offline with a local **SQLite** database. Optional GitHub token adds richer signals (changed files, CI status, reviews).

---

## 0) Repo layout

```
cursor-agents-review/
├─ scraper/                 # Playwright TS scraper for cursor.com/agents
│  ├─ src/
│  │  ├─ login.ts
│  │  ├─ scrape.ts
│  │  ├─ persist.ts
│  │  └─ types.ts
│  ├─ package.json
│  └─ playwright.config.ts
├─ server/                  # FastAPI MCP server + scoring
│  ├─ main.py               # FastAPI app exposing MCP tools
│  ├─ db.py                 # SQLite accessors
│  ├─ scoring.py            # Heuristic scoring of PRs
│  ├─ github.py             # Optional GitHub enrichment
│  ├─ recommend.py          # Next-step recommendations & roadmap nudge
│  └─ requirements.txt
├─ shared/
│  ├─ schema.sql            # DB schema
│  └─ config.example.env
└─ README.md                # This file
```

---

## 1) Quick start

### Prereqs

- Node 20+
- Python 3.10+
- `playwright install` will fetch browsers on first run

### Configure env

Copy and edit the example:

```bash
cp shared/config.example.env .env
```

`.env` keys (all optional except DB path):

```
DB_PATH=./cursor_agents.db
# GitHub (optional, but recommended for PR enrichment)
GITHUB_TOKEN=ghp_...
# Scoring knobs (optional)
MINUTES_LONG_RUN=18
HIGH_CHURN_LINES=500
```

### One-time login to Cursor web

```bash
cd scraper
pnpm i  # or npm i / yarn
pnpm playwright install
pnpm run login
# complete interactive login in the opened browser; auth saved to auth.json
```

### Scrape your Agent runs

```bash
pnpm run scrape
# writes runs + discovered PR links into ../cursor_agents.db
```

### Start MCP server

```bash
cd ../server
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 7399
```

### Add MCP to Cursor (Settings → MCP)

Point to `http://127.0.0.1:7399/mcp`. Then in Cursor, ask:

> Review my last 10 agent runs and rank the PRs needing human attention.

---

## 2) Database schema

```sql
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
```

---

## 3) Scoring dimensions and rubric

Each PR gets 0–10 on these axes, plus a final **Attention Score** (0–100):

1. **Code Quality** – lint signals (if available), ratio of added lines to files, presence of obvious anti-patterns (long files >1,000 LOC added, duplicated blocks).
2. **Verbosity** – comments/doc deltas vs code deltas; penalize gratuitous logging / debug prints.
3. **Efficiency** – hotspots touched, big‑O regressors (heuristic: heavy loops added on large collections, nested loops), unnecessary allocations.
4. **Stability** – CI status, presence of new/updated tests, coverage proxies, churn.
5. **Robustness** – error handling, input validation, boundary checks.
6. **Clean Code** – naming consistency, function length percentiles, cyclomatic hints via simple token heuristics.
7. **Reusability** – modularity, extraction into libs/utils, public API clarity.
8. **Ingenuity** – non‑obvious but sound solutions, algorithmic elegance (keyword heuristics + structure).
9. **Need for Human Attention** – composite risk (large churn, failed CI, low tests, low stability/robustness, touches critical paths).

The scoring is **heuristic and explainable** (rule‑based), with optional LLM refinement if you export `OPENAI_API_KEY` later.

---

## 4) Scripts & code

### `scraper/package.json`

```json
{
  "name": "cursor-agents-scraper",
  "private": true,
  "type": "module",
  "scripts": {
    "login": "tsx src/login.ts",
    "scrape": "tsx src/scrape.ts"
  },
  "dependencies": {
    "better-sqlite3": "^9.4.0",
    "dotenv": "^16.4.5",
    "playwright": "^1.46.0",
    "tsx": "^4.19.0"
  }
}
```

### `scraper/playwright.config.ts`

```ts
import { defineConfig } from '@playwright/test';
export default defineConfig({
  use: { baseURL: 'https://cursor.com', viewport: { width: 1400, height: 900 } },
  timeout: 120_000
});
```

### `scraper/src/types.ts`

```ts
export type RunRow = {
  id: string;
  title?: string;
  prompt?: string;
  status?: string;
  repo?: string;
  branch?: string;
  created_at?: string;
  updated_at?: string;
  duration_seconds?: number;
  pr_url?: string;
  details_url?: string;
  raw?: any;
};
```

### `scraper/src/persist.ts`

```ts
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
```

### `scraper/src/login.ts`

```ts
import 'dotenv/config';
import { chromium } from 'playwright';
import { fileURLToPath } from 'url';

(async () => {
  const browser = await chromium.launchPersistentContext('', { headless: false });
  const page = await browser.newPage();
  await page.goto('https://cursor.com/agents');
  console.log('Complete login in the opened window; close it when /agents loads.');
  await page.waitForURL(/cursor\.com\/agents/, { timeout: 5 * 60_000 });
  await browser.storageState({ path: 'auth.json' });
  console.log('Saved auth.json');
  await browser.close();
})();
```

### `scraper/src/scrape.ts`

```ts
import 'dotenv/config';
import { chromium } from 'playwright';
import { openDb, upsertRun } from './persist.js';

const DB_PATH = process.env.DB_PATH || '../cursor_agents.db';

(async () => {
  const db = openDb(DB_PATH);
  const browser = await chromium.launchPersistentContext('', {
    headless: true, storageState: 'auth.json'
  });
  const page = await browser.newPage();
  await page.goto('https://cursor.com/agents');
  await page.waitForLoadState('networkidle');

  // Resilient selection: assume cards/rows with links to details
  const items = await page.$$('[role="listitem"], [data-testid="agent-run"], a[href^="/agents/"]');
  const seen = new Set<string>();

  for (const el of items) {
    const href = await el.getAttribute('href');
    const detailsUrl = href?.startsWith('/agents/') ? `https://cursor.com${href}` : null;
    if (!detailsUrl || seen.has(detailsUrl)) continue;
    seen.add(detailsUrl);

    const dPage = await browser.newPage();
    await dPage.goto(detailsUrl);
    await dPage.waitForLoadState('networkidle');

    // Heuristic extraction: titles, status badges, repo, PR link
    const title = (await dPage.locator('h1, [data-testid="title"], [role="heading"]').first().textContent() || '').trim();
    const status = (await dPage.locator('[data-status], [data-testid*="status"], text=/Status/i').first().textContent() || '').trim();
    const prompt = (await dPage.locator('text=/Prompt/i').locator('xpath=..').textContent().catch(()=>'')).trim();
    const repoText = (await dPage.locator('a[href*="github.com" i]').first().textContent().catch(()=>''))?.trim();

    const prEl = dPage.locator('a[href*="/pull/"]');
    const prUrl = await prEl.first().getAttribute('href').catch(()=>null);

    const tCreated = await dPage.locator('time').first().getAttribute('datetime').catch(()=>null);
    const tUpdated = await dPage.locator('time').last().getAttribute('datetime').catch(()=>null);

    const id = detailsUrl.split('/').pop()!;

    upsertRun(db, {
      id,
      title,
      prompt,
      status,
      repo: repoText || undefined,
      branch: undefined,
      created_at: tCreated || undefined,
      updated_at: tUpdated || undefined,
      duration_seconds: undefined,
      pr_url: prUrl?.startsWith('http') ? prUrl : (prUrl ? `https://github.com${prUrl}` : undefined),
      details_url: detailsUrl,
      raw: { title, status, repoText }
    });

    await dPage.close();
  }

  await browser.close();
  console.log(`Scraped ${seen.size} runs → ${DB_PATH}`);
})();
```

---

## 5) MCP server

### `server/requirements.txt`

```
fastapi==0.115.0
uvicorn==0.30.6
pydantic==2.8.2
python-dotenv==1.0.1
httpx==0.27.2
python-multipart==0.0.9
jinja2==3.1.4
```

### `server/db.py`

```py
import os, sqlite3
from pathlib import Path

DB_PATH = os.getenv('DB_PATH', './cursor_agents.db')

def conn():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def get_runs(limit=50):
    with conn() as c:
        return c.execute('SELECT * FROM runs ORDER BY updated_at DESC LIMIT ?', (limit,)).fetchall()

def get_recent_prs(limit=50):
    with conn() as c:
        return c.execute('SELECT * FROM prs ORDER BY updated_at DESC LIMIT ?', (limit,)).fetchall()

def upsert_pr(row: dict):
    keys = ','.join(row.keys())
    q = ','.join([f':{k}' for k in row.keys()])
    update = ','.join([f'{k}=excluded.{k}' for k in row.keys() if k!='id'])
    sql = f'INSERT INTO prs ({keys}) VALUES ({q}) ON CONFLICT(id) DO UPDATE SET {update}'
    with conn() as c:
        c.execute(sql, row)
```

### `server/github.py`

```py
import os, re, httpx
from .db import upsert_pr

GH = os.getenv('GITHUB_TOKEN')
H = {'Authorization': f'Bearer {GH}'} if GH else {}

PR_ID_RE = re.compile(r'https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)')

async def enrich_pr(client: httpx.AsyncClient, pr_url: str):
    m = PR_ID_RE.match(pr_url)
    if not m: return None
    owner, repo, num = m.group(1), m.group(2), int(m.group(3))
    base = f'https://api.github.com/repos/{owner}/{repo}/pulls/{num}'
    r = await client.get(base, headers=H)
    if r.status_code != 200: return None
    j = r.json()
    files = await client.get(base + '/files', headers=H)
    fjs = files.json() if files.status_code==200 else []

    has_tests = any('/test' in f['filename'] or f['filename'].endswith(('_test.py','Test.java','.spec.ts','.test.ts','.test.tsx')) for f in fjs)
    doc_ratio = sum(1 for f in fjs if f['filename'].lower().startswith(('docs/','doc/','readme'))) / max(len(fjs),1)

    ci = 'unknown'
    # Best-effort: use combined status
    repourl = f'https://api.github.com/repos/{owner}/{repo}'
    # modern checks API would need sha; keep simple for scaffold

    row = {
      'id': f'{owner}/{repo}#{num}',
      'owner': owner,
      'repo': repo,
      'number': num,
      'title': j.get('title'),
      'author': j.get('user',{}).get('login'),
      'state': 'merged' if j.get('merged_at') else j.get('state'),
      'html_url': j.get('html_url'),
      'created_at': j.get('created_at'),
      'updated_at': j.get('updated_at'),
      'merged_at': j.get('merged_at'),
      'additions': j.get('additions') or 0,
      'deletions': j.get('deletions') or 0,
      'changed_files': j.get('changed_files') or len(fjs),
      'draft': 1 if j.get('draft') else 0,
      'review_count': j.get('review_comments') or 0,
      'ci_status': ci,
      'has_tests': 1 if has_tests else 0,
      'doc_touch_ratio': float(doc_ratio),
      'diff_stats': json_dumps_safe({'files': fjs[:50]})
    }
    upsert_pr(row)
    return row

def json_dumps_safe(o):
    import json
    try: return json.dumps(o)
    except Exception: return '{}'
```

### `server/scoring.py`

```py
from dataclasses import dataclass

@dataclass
class Scores:
    code_quality: float
    verbosity: float
    efficiency: float
    stability: float
    robustness: float
    clean_code: float
    reusability: float
    ingenuity: float
    attention: float

# Simple, explainable heuristics. Tunable via env.

def clamp(x, lo=0, hi=10):
    return max(lo, min(hi, x))

def score_pr(pr: dict) -> Scores:
    add = pr.get('additions', 0) or 0
    dels = pr.get('deletions', 0) or 0
    files = pr.get('changed_files', 0) or 0
    has_tests = bool(pr.get('has_tests'))
    doc_ratio = float(pr.get('doc_touch_ratio') or 0)
    draft = bool(pr.get('draft'))
    state = pr.get('state','open')

    churn = add + dels
    size_penalty = 0 if churn < 50 else 2 if churn < 200 else 4 if churn < 600 else 6

    code_quality = clamp(9 - size_penalty + (1 if has_tests else -1))
    verbosity = clamp(5 + (doc_ratio*5) - (churn/800))    # low doc → lower score
    efficiency = clamp(7 - (churn/400))                   # big diffs presumed less efficient
    stability = clamp((8 if has_tests else 5) + (2 if state=='merged' else 0) - (2 if draft else 0))
    robustness = clamp((6 if has_tests else 4) + (1 if doc_ratio>0.1 else 0))
    clean_code = clamp(7 - size_penalty/2)
    reusability = clamp(6 + (doc_ratio*2) - (files/50))
    ingenuity = clamp(5 + min(3, (doc_ratio*2)) - (size_penalty/3))

    # Attention: higher if risky or failing
    risk = 0
    if churn > 600: risk += 30
    if not has_tests: risk += 20
    if draft: risk += 10
    if files > 30: risk += 10
    if state == 'open': risk += 15

    attention = max(0, min(100, 30 + risk - (doc_ratio*10)))

    return Scores(code_quality, verbosity, efficiency, stability, robustness, clean_code, reusability, ingenuity, attention)

def scores_to_dict(s: Scores):
    return {
        'code_quality': s.code_quality,
        'verbosity': s.verbosity,
        'efficiency': s.efficiency,
        'stability': s.stability,
        'robustness': s.robustness,
        'clean_code': s.clean_code,
        'reusability': s.reusability,
        'ingenuity': s.ingenuity,
        'attention': s.attention,
    }
```

### `server/recommend.py`

```py
from .scoring import Scores

NEXT_STEPS_TEMPLATES = {
  'tests_missing': "Add/extend unit tests targeting new logic and edge cases; gate with CI.",
  'docs_low': "Augment README/inline docs; explain rationale and trade-offs.",
  'too_large': "Split PR into cohesive commits/modules; isolate refactors from logic changes.",
  'needs_review': "Request review from owner of touched module; add checklists.",
  'perf_risk': "Benchmark hotspots; add micro-bench or profiling notes.",
}

def recommendations(scores: Scores, pr: dict):
    recs = []
    if scores.stability < 6 or not pr.get('has_tests'): recs.append(NEXT_STEPS_TEMPLATES['tests_missing'])
    if scores.verbosity < 5: recs.append(NEXT_STEPS_TEMPLATES['docs_low'])
    if scores.clean_code < 6: recs.append(NEXT_STEPS_TEMPLATES['too_large'])
    if scores.attention > 60: recs.append(NEXT_STEPS_TEMPLATES['needs_review'])
    if scores.efficiency < 5: recs.append(NEXT_STEPS_TEMPLATES['perf_risk'])
    return recs[:3]

# Lightweight "roadmap" nudge based on recent PRs

def roadmap_hint(aggregate):
    # aggregate: list of {'scores': Scores, 'pr': dict}
    if not aggregate:
        return "No data yet."
    many_large = sum(1 for a in aggregate if a['scores'].attention>70) >= max(2, len(aggregate)//3)
    low_docs = sum(1 for a in aggregate if a['scores'].verbosity<5) >= max(2, len(aggregate)//4)
    if many_large and low_docs:
        return "Prioritize a documentation and testing sprint; enforce PR size guardrails and module ownership."
    if many_large:
        return "Adopt PR size guardrails and enforce CI checks before agent merges."
    if low_docs:
        return "Schedule a docs pass: READMEs, ADRs, and code comments for recent modules."
    return "On track. Consider extracting common utilities into a shared library for reusability."
```

### `server/main.py`

```py
import os, asyncio
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
import httpx
from .db import get_runs, get_recent_prs
from .github import enrich_pr
from .scoring import score_pr, scores_to_dict
from .recommend import recommendations, roadmap_hint

load_dotenv()
app = FastAPI(title='Cursor Agents MCP')

# MCP schema: expose a simple tool contract at /mcp
@app.get('/mcp')
async def mcp_manifest():
    return {
      "tools": [
        {"name":"list_tasks","description":"List recent Cursor Agent runs","input_schema":{"type":"object","properties":{"limit":{"type":"integer"}},"required":[]}},
        {"name":"review_prs","description":"Rank recent PRs and recommend next steps","input_schema":{"type":"object","properties":{"limit":{"type":"integer"}},"required":[]}},
        {"name":"task","description":"Fetch details for a task (run id)","input_schema":{"type":"object","properties":{"id":{"type":"string"}},"required":["id"]}}
      ]
    }

@app.post('/tools/list_tasks')
async def list_tasks(body: dict):
    limit = int(body.get('limit') or 25)
    runs = [dict(r) for r in get_runs(limit)]
    return {"content": runs}

@app.post('/tools/task')
async def task(body: dict):
    # In this scaffold, runs are flat; for details, re-open details_url client-side
    run_id = body['id']
    runs = [dict(r) for r in get_runs(200) if dict(r)['id']==run_id]
    return {"content": runs[0] if runs else None}

@app.post('/tools/review_prs')
async def review_prs(body: dict):
    limit = int(body.get('limit') or 20)
    prs = [dict(r) for r in get_recent_prs(limit)]
    if not prs:
        # opportunistically enrich from runs if DB is empty
        runs = [dict(r) for r in get_runs(100)]
        pr_urls = [r.get('pr_url') for r in runs if r.get('pr_url')]
        async with httpx.AsyncClient(timeout=20) as client:
            for url in pr_urls[:limit]:
                await enrich_pr(client, url)
        prs = [dict(r) for r in get_recent_prs(limit)]

    scored = []
    for pr in prs:
        s = score_pr(pr)
        scored.append({
          'pr': {
            'id': pr['id'], 'title': pr['title'], 'url': pr['html_url'], 'state': pr['state'],
            'author': pr.get('author'), 'additions': pr.get('additions'), 'deletions': pr.get('deletions'),
            'changed_files': pr.get('changed_files'), 'has_tests': bool(pr.get('has_tests'))
          },
          'scores': scores_to_dict(s),
          'recommendations': recommendations(s, pr)
        })

    ranked = sorted(scored, key=lambda x: x['scores']['attention'], reverse=True)
    hint = roadmap_hint([{ 'scores': score_pr(pr), 'pr': pr } for pr in prs])
    return {"content": {"ranked": ranked, "roadmap_hint": hint}}
```

---

## 6) Workflow you’ll use

1. `pnpm run login` (once)
2. `pnpm run scrape` whenever you want fresh runs/PR URLs
3. `uvicorn main:app` to expose MCP
4. In Cursor, call tools in natural language: *“review my PRs and tell me top three needing human attention, with next steps.”*

Automate #2 with `cron` or a `just`/`make` target.

---

## 7) Roadmap / extensions

- Add **LLM refinement** for qualitative axes (ingenuity, clean code) with traceable rationales.
- Wire CI statuses via Checks API (needs commit SHA → fetch from PR head).
- Add **module ownership map** to boost “need human attention” when an agent edits owned code without reviewer.
- Parse **Cursor run logs** for intermediate errors to weight stability.
- Build a minimal web UI over SQLite (Jinja2 templates) for human triage.

---

## 8) Troubleshooting

- **Scraper logs in but saves nothing** → run with `headful` once and verify `/agents` shows runs; selectors are defensive but can drift; upgrade Playwright.
- **No PRs show up** → Agents may not have created PRs; run `review_prs` after pushing a PR link into `runs.pr_url` manually to test pathway.
- **GitHub rate limits** → Set `GITHUB_TOKEN`.

---

## 9) License

MIT. Use at will.

