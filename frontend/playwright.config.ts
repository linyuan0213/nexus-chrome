import { defineConfig } from '@playwright/test';

/**
 * e2e 需后端运行（默认 http://127.0.0.1:9850）：
 *   uv run python main.py
 *   cd frontend && pnpm test:e2e
 */
export default defineConfig({
  testDir: './tests/e2e',
  timeout: 60_000,
  retries: 0,
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'pnpm dev',
    url: 'http://127.0.0.1:5173/ui/',
    reuseExistingServer: true,
    timeout: 30_000,
  },
});
