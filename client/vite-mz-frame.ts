import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { build, type Plugin } from 'vite'

// The editor that runs inside a magazine page being edited
// (src/cappe/magazine/frame/). That page is a frame sandboxed with scripts
// but not our origin, so it can't load our script files: this bundles the
// runtime, Tiptap included, into one script and its stylesheet, exported as
// strings from `virtual:mz-frame` for EditFrame to write into the page.
// Built once per build (again when a frame file changes in dev); an empty
// stub under Vitest, whose tests drive the frame's messages themselves.

const ID = 'virtual:mz-frame'
const RESOLVED = `\0${ID}`
const DIR = 'src/cappe/magazine/frame'

type Bundle = { script: string; style: string }

async function bundle(root: string, minify: boolean): Promise<Bundle> {
  const out = await build({
    configFile: false,
    root,
    logLevel: 'warn',
    define: { 'process.env.NODE_ENV': JSON.stringify('production') },
    esbuild: { legalComments: 'none' },
    build: {
      write: false,
      minify,
      sourcemap: false,
      copyPublicDir: false,
      emptyOutDir: false,
      lib: { entry: path.resolve(root, DIR, 'index.ts'), formats: ['iife'], name: 'mzFrame', fileName: () => 'mz-frame.js' },
    },
  })
  const outputs = (Array.isArray(out) ? out : [out]).flatMap((o) => ('output' in o ? o.output : []))
  const chunk = outputs.find((o) => o.type === 'chunk')
  if (!chunk || chunk.type !== 'chunk') throw new Error('mz-frame: no script was built')
  // Written into a <script> element: nothing in it may end that element.
  const script = chunk.code.replace(/<\/(script)/gi, '<\\/$1')
  if (/<!--|<script/i.test(script)) throw new Error('mz-frame: the script holds markup that would break the page it is written into')
  const style = (await readFile(path.resolve(root, DIR, 'frame.css'), 'utf-8')).replace(/<\/(style)/gi, '')
  return { script, style }
}

export function mzFrame(): Plugin {
  let root = process.cwd()
  let minify = true
  let built: Promise<Bundle> | null = null
  return {
    name: 'cappe-mz-frame',
    configResolved(config) {
      root = config.root
      minify = config.command === 'build'
    },
    resolveId: (id) => (id === ID ? RESOLVED : null),
    async load(id) {
      if (id !== RESOLVED) return null
      if (process.env.VITEST) return 'export const frameScript = ""\nexport const frameStyle = ""'
      built ??= bundle(root, minify)
      const { script, style } = await built
      return `export const frameScript = ${JSON.stringify(script)}\nexport const frameStyle = ${JSON.stringify(style)}`
    },
    // In dev, a change to the runtime builds it again and reloads the editor —
    // also a change to what it imports from canvas/ (rt.ts, fields.ts), which
    // the dashboard uses too, so both sides keep the same rules.
    handleHotUpdate({ file, server }) {
      const inFrame = file.startsWith(path.resolve(root, DIR) + path.sep)
      if (!inFrame && !file.startsWith(path.resolve(root, DIR, '..', 'canvas') + path.sep)) return
      built = null
      const mod = server.moduleGraph.getModuleById(RESOLVED)
      if (mod) server.moduleGraph.invalidateModule(mod)
      server.ws.send({ type: 'full-reload' })
      return inFrame ? [] : undefined
    },
  }
}
