import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    // Same-origin only. The frontend must never hardcode localhost:8000 —
    // it breaks the moment someone runs on a different host.
    proxy: {
      '/api': { target: 'http://backend:8000', changeOrigin: true, ws: true },
    },
  },
})
