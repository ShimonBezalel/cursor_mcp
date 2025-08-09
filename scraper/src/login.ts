import './env.js';
import 'dotenv/config';
import { chromium } from 'playwright';

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