import './env.js';
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
  await page.goto('https://cursor.com/agents', { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle');

  const items = await page.$$('[role="listitem"], [data-testid="agent-run"], a[href^="/agents/"]');
  const seen = new Set<string>();

  for (const el of items) {
    const href = await el.getAttribute('href').catch(() => null);
    const detailsUrl = href && href.startsWith('/agents/') ? `https://cursor.com${href}` : null;
    if (!detailsUrl || seen.has(detailsUrl)) continue;
    seen.add(detailsUrl);

    const dPage = await browser.newPage();

    // Retry navigation briefly for robustness
    let loaded = false;
    for (let attempt = 0; attempt < 2 && !loaded; attempt++) {
      try {
        await dPage.goto(detailsUrl, { waitUntil: 'domcontentloaded' });
        await dPage.waitForLoadState('networkidle');
        loaded = true;
      } catch {}
    }
    if (!loaded) {
      await dPage.close();
      continue;
    }

    const title = (await dPage.locator('h1, [data-testid="title"], [role="heading"]').first().textContent().catch(() => '') || '').trim();
    const status = (await dPage.locator('[data-status], [data-testid="status"]').first().textContent().catch(() => '') || '').trim();

    // Repo text may be in various anchors; pick the first plausible
    const repoText = (await dPage.locator('a[href*="github.com" i]').first().textContent().catch(() => '') || '').trim();
    const prEl = dPage.locator('a[href*="/pull/"]');
    const prUrlRaw = await prEl.first().getAttribute('href').catch(() => null);
    const prUrl = prUrlRaw
      ? (prUrlRaw.startsWith('http') ? prUrlRaw : `https://github.com${prUrlRaw}`)
      : undefined;

    const timeEls = dPage.locator('time');
    const tCreated = await timeEls.nth(0).getAttribute('datetime').catch(() => null);
    const tUpdated = await timeEls.last().getAttribute('datetime').catch(() => null);

    const id = detailsUrl.split('/').pop() || undefined;
    if (!id) {
      await dPage.close();
      continue;
    }

    upsertRun(db, {
      id,
      title: title || undefined,
      prompt: undefined,
      status: status || undefined,
      repo: repoText || undefined,
      branch: undefined,
      created_at: tCreated || undefined,
      updated_at: tUpdated || undefined,
      duration_seconds: undefined,
      pr_url: prUrl,
      details_url: detailsUrl,
      raw: { title, status, repoText, detailsUrl }
    });

    await dPage.close();
  }

  await browser.close();
  console.log(`Scraped ${seen.size} runs → ${DB_PATH}`);
})();