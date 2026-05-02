import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
const backendTarget = process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8001'
const backendWsTarget = backendTarget.replace(/^http/, 'ws')

export default defineConfig({
  plugins: [react()],
  build: {
    // Emit source maps alongside JS bundles and include a
    // //# sourceMappingURL= comment so browsers resolve stack traces to
    // original TSX file + line numbers. Critical for the client-error
    // reporter — prod stacks would otherwise be mangled minified names.
    // Source isn't a secret; the same code is already in git.
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-three': ['three'],
          'vendor-framer': ['framer-motion'],
          'vendor-react': ['react', 'react-dom'],
        }
      }
    }
  },
  server: {
    port: 5174,
    proxy: {
      '/api': {
        target: backendTarget,
        changeOrigin: true,
        ws: true,
      },
      '/ws': {
        target: backendWsTarget,
        ws: true,
        changeOrigin: true,
      },
      '/uploads': {
        target: backendTarget,
        changeOrigin: true,
      },
      '/sitemap.xml': {
        target: backendTarget,
        changeOrigin: true,
      },
      '/robots.txt': {
        target: backendTarget,
        changeOrigin: true,
      },
    },
  },
  esbuild: {
    drop: process.env.NODE_ENV === 'production' ? ['console', 'debugger'] : [],
  },
})
