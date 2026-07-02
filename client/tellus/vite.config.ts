import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Tell-Us is a SEPARATE Vite app served by the same matcha-frontend nginx
// container at /tellus/. base='/tellus/' makes assets emit under /tellus/assets/
// so they don't collide with the main app's /assets/. API is called same-origin
// at /api/tellus (no CORS). Dev server runs on its own port with the same
// /api → :8001 proxy as the main client.
const backendTarget = process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8001'

export default defineConfig({
  base: '/tellus/',
  plugins: [react()],
  server: {
    // 5191 — outside the main client's fallback range (5175-5190 in
    // dev-remote.sh) and matched by the main vite.config's '/tellus' proxy
    // default, so http://localhost:5174/tellus/ reaches this server in dev.
    // Explicit IPv4 host: 'localhost' can bind ::1 only (macOS), which the
    // main app's 127.0.0.1 proxy target can't reach (ECONNREFUSED).
    host: '127.0.0.1',
    port: 5191,
    proxy: {
      '/api': { target: backendTarget, changeOrigin: true },
    },
  },
})
