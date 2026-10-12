import { configDefaults, defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

const backend = process.env.VITE_BACKEND_URL ?? 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    proxy: {
      '/api': { target: backend, ws: true },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test-setup.ts',
    exclude: [...configDefaults.exclude, 'e2e/**'],
  },
});