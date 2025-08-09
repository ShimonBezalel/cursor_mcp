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

    const title = (await dPage.locator('h1').first().textContent() || '').trim();
    const status = (await dPage.locator('[data-status]').first().textContent() || '').trim();
    const prompt = '';
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