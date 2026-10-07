import { defineConfig, devices } from '@playwright/test'

/**
 * Dev-tooling config — NOT the product E2E suite.
 *
 * Covers the developer surfaces in docker-compose.yml that the demo does not
 * touch: Adminer (DB GUI), Mailpit, and the dev panel's own video endpoints.
 * These run against real containers; nothing is mocked, because the failure
 * mode this exists to catch IS a container being wired up wrong.
 *
 * Deliberately separate from playwright.config.ts: the product suite's
 * global-setup deletes non-seed users, and these tests must not depend on or
 * disturb that data.
 */
export default defineConfig({
  testDir: './tests-devtools',
  fullyParallel: false,
  retries: 0,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  reporter: [['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})