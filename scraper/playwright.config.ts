import { defineConfig } from '@playwright/test';
export default defineConfig({
  use: { baseURL: 'https://cursor.com', viewport: { width: 1400, height: 900 } },
  timeout: 120000
});