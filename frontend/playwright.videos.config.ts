import { defineConfig, devices } from '@playwright/test'

/** Config for the evidence videos. Separate from playwright.config.ts so the
 *  normal suite stays fast and never records.
 *
 *  Usage:
 *    docker compose exec -T frontend npx playwright test -c playwright.videos.config.ts
 *    ./scripts/build-videos.sh          # composites + captions afterwards
 */
export default defineConfig({
  testDir: './tests-videos',
  // Accumulated "Tomas Nowak T82" test users make the recordings both slower and
  // visibly sloppy — the videos are meant to show the product, not our debris.
  globalSetup: './tests/global-setup.ts',
  // The videos must show a settled app, not a loading spinner.
  timeout: 180_000,
  expect: { timeout: 15_000 },
  // One at a time: these share one database and two of them use two browsers.
  // Parallelism would have two videos recording each other's test users.
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  outputDir: './videos-raw',
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5173',
    video: { mode: 'on', size: { width: 1280, height: 800 } },
    trace: 'off',
    screenshot: 'off',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // Must match the video size or Playwright letterboxes the recording.
        viewport: { width: 1280, height: 800 },
      },
    },
  ],
})