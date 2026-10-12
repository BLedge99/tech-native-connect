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
    //
    // changeOrigin stays OFF. It rewrites the `Origin` header along with Host,
    // so the backend's WebSocket origin check saw `http://backend:8000` and
    // refused every legitimate connection from the browser. Browsers cannot
    // forge Origin, so passing the real one through is both correct and
    // necessary.
    proxy: {
      '/api': { target: 'http://backend:8000', ws: true },
    },
  },
})
