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
    // NO custom manualChunks. Hand-chunking React into its own vendor chunk
    // repeatedly caused a cross-chunk init-order race in React 19 where the
    // first React.lazy route crashed with "undefined is not an object
    // (evaluating _result.default)" — the lazy payload's _result was read
    // before the React chunk initialized. Both the array AND function forms
    // hit this. Vite/Rollup's default chunking keeps React with the entry and
    // orders dynamic-import deps correctly, so lazy routes resolve safely.
    // Chunks are still content-hashed (cache-busting intact). Do not re-add a
    // react/react-dom manualChunks rule.
  },
  server: {
    port: 5174,
    proxy: {
      // Tell-Us is a SEPARATE Vite app (client/tellus, base '/tellus/') with
      // its own dev server. Proxying it here makes dev match prod (one origin
      // serves both apps), so /tellus/* works on this port too. ws:true keeps
      // the tellus HMR websocket alive through the proxy. Target defaults to
      // the tellus dev server's fixed port; dev-remote.sh overrides via env.
      '/tellus': {
        target: process.env.VITE_TELLUS_TARGET || 'http://127.0.0.1:5191',
        changeOrigin: true,
        ws: true,
      },
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
