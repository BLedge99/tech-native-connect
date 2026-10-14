import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const contentSecurityPolicy = (styleSource: string) =>
  `default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; script-src 'self'; style-src ${styleSource}; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self' ws: wss:`

const securityHeaders = {
  'X-Content-Type-Options': 'nosniff',
  'X-Frame-Options': 'DENY',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    headers: {
      ...securityHeaders,
      'Content-Security-Policy': contentSecurityPolicy("'self' 'unsafe-inline'"),
    },
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
  preview: {
    headers: {
      ...securityHeaders,
      'Content-Security-Policy': contentSecurityPolicy("'self'"),
    },
  },
})
