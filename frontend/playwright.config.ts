import {defineConfig, devices} from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  retries: 0,
  use: {baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:5173', ...devices['Desktop Chrome']},
});
