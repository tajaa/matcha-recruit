import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Oceanlab is a SEPARATE Vite app served by the same matcha-frontend nginx
// container at /oceanlab/. base='/oceanlab/' makes assets emit under
// /oceanlab/assets/ so they don't collide with the main app's /assets/. API
// is called same-origin at /api/oceanlab (no CORS). Dev server runs on its
// own port with the same /api -> :8001 proxy as the main client.
const backendTarget = process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8001'

export default defineConfig({
  base: '/oceanlab/',
  plugins: [react(), tailwindcss()],
  server: {
    // 5201 — outside the main client's fallback range (5175-5190) and
    // tellus's dev port (5191), matched by the main vite.config's
    // '/oceanlab' proxy default.
    host: '127.0.0.1',
    allowedHosts: ['host.docker.internal'],
    port: 5201,
    proxy: {
      '/api': { target: backendTarget, changeOrigin: true },
    },
  },
})
