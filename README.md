# Cursor Agents Scraper

- Set `DB_PATH` in `.env` (e.g., `DB_PATH=./cursor_agents.db`).
- Optionally set `SCHEMA_SQL_PATH` or place `shared/schema.sql` at repo root. The scraper will apply it on open; otherwise it creates a minimal `runs` table.
- From repo root:
  - `pnpm --filter ./scraper install`
  - `pnpm --filter ./scraper run login`
  - `pnpm --filter ./scraper run scrape`