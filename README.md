# Cursor Agents Review Infra – Scraper + MCP Server

This repo lets you scrape Cursor Agent runs from `cursor.com/agents` into a local SQLite database and expose them as Model Context Protocol (MCP) tools via a small FastAPI server that Cursor can connect to.

The design and architecture are described in `cursor_agents_review_infra_scraper_mcp_scoring.md`.

---

## Quickstart (TL;DR)

- Prereqs: Node 18+, Python 3.10+, SQLite3, curl
- 1) Install scraper deps and Playwright browsers
- 2) Login once to Cursor via Playwright (saves `scraper/auth.json`)
- 3) Scrape runs → creates `cursor_agents.db` in repo root
- 4) Start the MCP HTTP server
- 5) Test with curl
- 6) Add the MCP URL in Cursor Settings → MCP

---

## 1) Install scraper

```bash
cd scraper
npm install
npx playwright install chromium
# Optional on Linux: installs system libs for headless Chromium
# npx playwright install-deps chromium
```

Env (optional): create `scraper/.env` if you want to override DB path.
- `DB_PATH` (default: `../cursor_agents.db`)

## 2) Login once (interactive)

This opens a browser for you to sign in to Cursor. When `/agents` loads, storage is saved to `scraper/auth.json`.

```bash
cd scraper
npm run login
```

## 3) Scrape agent runs

This visits `/agents`, opens each run details page, and writes records into a SQLite DB. By default, the DB is created at repo root as `cursor_agents.db`.

```bash
cd scraper
# Optional: override DB path for the scraper
# echo "DB_PATH=../cursor_agents.db" > .env
npm run scrape
```

You should see a message like:

```
Scraped N runs → ../cursor_agents.db
```

## 4) Start the MCP server

Create a virtualenv, install requirements, and start the HTTP server.

```bash
cd server
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Optional: override DB path for the server
# echo "DB_PATH=../cursor_agents.db" > .env
uvicorn main:app --host 127.0.0.1 --port 7399
```

Defaults:
- `DB_PATH` default resolves to `../cursor_agents.db` (repo root), matching the scraper default
- `APP_NAME` (default: `Cursor Agents MCP`)
- `APP_DESC` (default: `Expose scraped Cursor Agent runs and PRs as MCP tools`)

## 5) Verify with curl

- Get MCP manifest

```bash
curl -s http://127.0.0.1:7399/mcp | jq
```

- List recent runs (tasks)

```bash
curl -s -X POST http://127.0.0.1:7399/tools/list_tasks \
  -H 'content-type: application/json' \
  -d '{"limit": 5}' | jq
```

- Get a specific run by id (or omit `id` to get the most recent)

```bash
# Replace RUN_ID with an id returned from list_tasks
curl -s -X POST http://127.0.0.1:7399/tools/task \
  -H 'content-type: application/json' \
  -d '{"id": "RUN_ID"}' | jq
```

- List recent PRs referenced by runs

```bash
curl -s -X POST http://127.0.0.1:7399/tools/review_prs \
  -H 'content-type: application/json' \
  -d '{"limit": 10}' | jq
```

## 6) Add MCP server in Cursor

- Open Cursor Settings → Experimental → Model Context Protocol (MCP)
- Add a new HTTP MCP server with URL: `http://127.0.0.1:7399/mcp`
- Give it a name (e.g., `Cursor Agents MCP`)
- Save, then open the MCP tools panel in Cursor to invoke `list_tasks`, `task`, and `review_prs`

If you use a different host/port, adjust the URL accordingly.

---

## Repo structure

```
.
├─ scraper/
│  ├─ package.json
│  ├─ playwright.config.ts
│  └─ src/
│     ├─ login.ts         # interactive login, saves auth.json
│     ├─ scrape.ts        # headless scrape → SQLite DB
│     ├─ persist.ts       # schema + upsert
│     └─ types.ts
├─ server/
│  ├─ requirements.txt
│  └─ main.py             # FastAPI app exposing MCP + tools
│  └─ db.py               # read runs and recent PRs from DB
├─ cursor_agents_review_infra_scraper_mcp_scoring.md  # design doc
└─ README.md
```

## Notes

- The scraper persists browser state in `scraper/auth.json`. Re-run login if your session expires.
- The DB schema is created automatically by the scraper on first run.
- You can point both scraper and server to the same custom DB by setting `DB_PATH` in their respective `.env` files.
- If Playwright reports missing system libraries on Linux, run `npx playwright install-deps chromium`.

## Troubleshooting

- No runs returned: ensure you completed login and your Cursor workspace has agent runs visible at `/agents`.
- Server cannot find DB: check the `DB_PATH` used by scraper vs. server.
- CORS is not needed for MCP since Cursor reads the manifest and posts directly to endpoints.

---

## License

MIT (or project default)