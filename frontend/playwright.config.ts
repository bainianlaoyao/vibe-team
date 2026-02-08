import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e_browser',
  timeout: 30_000,
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:4173',
    trace: 'on-first-retry',
  },
  webServer: process.env.E2E_SKIP_WEBSERVER
    ? undefined
    : {
        command: 'npm run build && npm run preview -- --host 127.0.0.1 --port 4173',
        port: 4173,
        reuseExistingServer: true,
      },
});
