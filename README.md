# Cursor Agents Review

This repo contains a Playwright scraper and a FastAPI server exposing tools.

- Scraper: `scraper/`
- Server: `server/` with `/tools/review_prs`

Quick start server:

```bash
cd server
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m server.main
# POST http://127.0.0.1:7399/tools/review_prs with {}
```