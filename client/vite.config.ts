import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
const backendTarget = process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8001'
const backendWsTarget = backendTarget.replace(/^http/, 'ws')

// The landing (`/`, `/incidents`) is a lazy route, so the browser only learns
// about its chunks after the entry bundle has downloaded and run. This writes
// a small inline script into index.html that, on those two paths only, adds
// modulepreload links for the route's chunks and preloads its two headline
// fonts, so they download alongside the entry instead of after it. It also
// sets the dark page background before any JS runs. Build only; chunk names
// are read from the bundle, so there is nothing to keep in sync by hand.
const LANDING = 'src/pages/landing/scheduling/'
const LANDING_TABS: Record<string, string> = { '/': 'SchedulingTab.tsx', '/incidents': 'IncidentsTab.tsx' }
const LANDING_FONTS = /^assets\/(hanken-grotesk-latin|instrument-serif-italic-latin)-[\w-]+\.woff2$/
const cappeHost = process.env.VITE_CAPPE_HOST || 'gummfit.com'

function landingPreload(): Plugin {
  return {
    name: 'matcha-landing-preload',
    transformIndexHtml: {
      order: 'post',
      handler(_html, ctx) {
        if (!ctx.bundle) return
        const chunks = Object.values(ctx.bundle).flatMap((item) => (item.type === 'chunk' ? [item] : []))
        const byName = new Map(chunks.map((chunk) => [chunk.fileName, chunk]))
        const closure = (roots: string[]) => {
          const seen = new Set<string>()
          const visit = (name: string) => {
            if (seen.has(name)) return
            seen.add(name)
            byName.get(name)?.imports.forEach(visit)
          }
          roots.forEach(visit)
          return seen
        }
        // Not facadeModuleId: Rollup leaves it unset when a lazy module's chunk also carries code shared with others.
        const facade = (file: string) => chunks.find((chunk) => chunk.moduleIds.some((id) => id.endsWith(LANDING + file)))?.fileName
        const shell = facade('index.tsx')
        if (!shell) return
        // Already fetched by the entry's own <script> and modulepreload tags.
        const entry = closure(chunks.filter((chunk) => chunk.isEntry).map((chunk) => chunk.fileName))
        const scripts = Object.fromEntries(Object.entries(LANDING_TABS).map(([path, file]) => {
          const tab = facade(file)
          return [path, [...closure(tab ? [shell, tab] : [shell])].filter((name) => !entry.has(name)).map((name) => `/${name}`)]
        }))
        const fonts = Object.keys(ctx.bundle).filter((name) => LANDING_FONTS.test(name)).map((name) => `/${name}`)
        const code = `(function(){var h=location.hostname,s=${JSON.stringify(scripts)}[location.pathname];if(!s||h===${JSON.stringify(cappeHost)}||h===${JSON.stringify(`www.${cappeHost}`)})return;document.documentElement.setAttribute('data-marketing-board','');function add(rel,href,font){var l=document.createElement('link');l.rel=rel;l.href=href;if(font){l.as='font';l.type='font/woff2';l.crossOrigin=''}document.head.appendChild(l)}${JSON.stringify(fonts)}.forEach(function(f){add('preload',f,true)});s.forEach(function(f){add('modulepreload',f)})})()`
        return [{ tag: 'script', children: code, injectTo: 'head' }]
      },
    },
  }
}

export default defineConfig({
  plugins: [react(), landingPreload()],
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
    // Docker Desktop forwards the IPv4 loopback listener to containers via
    // host.docker.internal. Allow only that additional Host header so an
    // isolated agent can test the host-run dev stack.
    allowedHosts: ['host.docker.internal'],
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
      // Oceanlab is a SEPARATE Vite app (client/oceanlab, base '/oceanlab/')
      // with its own dev server. Same pattern as Tell-Us above.
      '/oceanlab': {
        target: process.env.VITE_OCEANLAB_TARGET || 'http://127.0.0.1:5201',
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
