import {defineConfig, devices} from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  retries: 0,
  // All browser workers share one disposable API/PostgreSQL. Bound CPU/DB contention
  // instead of hiding slow journeys behind retries or a larger per-test timeout.
  workers: 4,
  use: {baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:5173', ...devices['Desktop Chrome'],
    screenshot: 'only-on-failure', trace: 'retain-on-failure'},
});
