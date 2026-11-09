import { existsSync, readFileSync } from 'node:fs'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The per-run API token (created by ../dev.mjs) is added by the proxy, server side.
// It never reaches browser JavaScript, so other websites can't call the API.
function apiToken(): string {
  if (process.env.MG_API_TOKEN) return process.env.MG_API_TOKEN
  const file = new URL('../memoryguard/data/.api_token', import.meta.url)
  return existsSync(file) ? readFileSync(file, 'utf8').trim() : ''
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    host: 'localhost',
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq) => proxyReq.setHeader('x-memoryguard-token', apiToken()))
        },
      },
    },
  },
})
