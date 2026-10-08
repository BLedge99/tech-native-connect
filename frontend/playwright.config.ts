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
  //
  // 90s, not 30s. The demo-path test drives a whole journey — two registrations,
  // two profile completions, a match, a request, an accept, two threads, four
  // messages and a reload — and measures ~33s on this machine. It was set to
  // 30s, so it failed roughly one run in five while passing every assertion,
  // which is the worst possible failure: a flaky centrepiece. A genuine hang
  // still fails, because a hang runs to 180s+.
  timeout: 90_000,
  expect: { timeout: 10_000 },
  reporter: process.env.CI ? 'github' : [['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})