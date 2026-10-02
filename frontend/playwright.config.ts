import { defineConfig, devices } from '@playwright/test'

/** E2E config. specs/00_conventions.md §10.
 *
 * No network mocking. A test that mocks the network is not testing the demo,
 * and the demo is the thing most likely to break.
 */
export default defineConfig({
  testDir: './tests',
  // Clears accumulated test users before the run. Without it the suite goes
  // flaky after a few runs, which reads as an app bug and is not one.
  globalSetup: './tests/global-setup.ts',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  // Live chat depends on the socket being open; a tight timeout hides the bug
  // rather than fixing it.
  timeout: 30_000,
  expect: { timeout: 10_000 },
  reporter: process.env.CI ? 'github' : [['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})