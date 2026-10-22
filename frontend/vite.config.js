import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// The browser talks to this dev server only; /api and /ws are forwarded to the
// FastAPI backend. One origin means the session cookie just works (cookies are
// not shared between localhost and 127.0.0.1) and no CORS is involved.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '')
  const target = env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000'
  const proxy = {
    '/api': { target, changeOrigin: false },
    '/ws': { target, ws: true, changeOrigin: false },
  }

  return {
    plugins: [react(), tailwindcss()],
    server: { proxy },
    preview: { proxy },
  }
})
