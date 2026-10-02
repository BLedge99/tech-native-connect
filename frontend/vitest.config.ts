import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Separate from vite.config.ts: vitest bundles its own vite copy, and mixing
// them in one file produces a Plugin type conflict that is not worth solving.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    // Restrict to *.test.tsx under src. Without this, Vitest's default glob
    // also picks up tests/demo.spec.ts and fails on Playwright's
    // test.describe().
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    exclude: ['e2e/**', 'node_modules/**'],
  },
})
