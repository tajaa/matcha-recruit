// The magazine's own fonts (server routes/studio_fonts.py): a licensed font
// file uploaded once and set like any face, in every story of this magazine.
// The server keeps a clean TrueType copy and names it by a key of its own
// (`u-…`), never by the font's real name; taking one off the list leaves the
// pages that set it as they are.

import { useEffect, useMemo, useRef, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { CappeApiError } from '../../api'
import { studioApi, type SiteFont } from '../api'
import { families, loadSiteFonts } from './siteFonts'
import { familyName } from '../fonts/faces'
import { useStudio } from '../store/store'
import { useCtx } from './context'
import { Dialog } from './dialogs'

const ACCEPT = '.ttf,.otf,.woff,.woff2,font/ttf,font/otf,font/woff,font/woff2'
const WEIGHTS = [100, 200, 300, 400, 500, 600, 700, 800, 900]
const NONE: SiteFont[] = []

const message = (err: unknown, fallback: string) => {
  if (err instanceof CappeApiError) {
    if (err.status === 402) return 'Your own fonts come with a magazine plan.'
    return err.message || fallback
  }
  return err instanceof Error ? err.message : fallback
}

export default function FontsDialog() {
  const c = useCtx()
  const fonts = useStudio(c.store, (s) => s.fonts ?? NONE)
  const close = () => c.store.set({ dialog: null })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [name, setName] = useState('')
  const [weight, setWeight] = useState<number | ''>('')
  const [italic, setItalic] = useState(false)
  const [licence, setLicence] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const groups = useMemo(() => families(fonts), [fonts])

  useEffect(() => { void loadSiteFonts(c).catch((err) => setError(message(err, 'Couldn’t load your fonts.'))) }, [c])
  // Each family's name shown in its own first face.
  useEffect(() => { for (const g of groups) void c.fonts.ensure(g.faces[0]).catch(() => {}) }, [c, groups])

  const pick = (f: File | null) => {
    setFile(f)
    if (f && !name) setName(f.name.replace(/\.(ttf|otf|woff2?)$/i, '').replace(/[-_](regular|bold|italic|light|medium|black|thin|semibold|extrabold)+$/i, '').replace(/[-_]+/g, ' ').slice(0, 60))
  }

  const upload = async () => {
    if (!file || !name.trim() || !licence) return
    setBusy(true); setError(null)
    try {
      const font = await studioApi.uploadFont(c.siteId, file, { name: name.trim(), licence, ...(weight !== '' ? { weight, italic } : italic ? { italic } : {}) })
      await loadSiteFonts(c)
      await c.fonts.ensure(font).catch(() => {})
      setFile(null); setWeight(''); setItalic(false)
      if (input.current) input.current.value = ''
    } catch (err) {
      setError(message(err, 'Couldn’t add that font.'))
    } finally {
      setBusy(false)
    }
  }

  const rename = async (key: string, current: string) => {
    const next = window.prompt('Rename this font', current)?.trim()
    if (!next || next === current) return
    try {
      await studioApi.renameFontFamily(c.siteId, key, next)
      await loadSiteFonts(c)
    } catch (err) {
      setError(message(err, 'Couldn’t rename it.'))
    }
  }

  const remove = async (font: SiteFont) => {
    try {
      await studioApi.hideFont(c.siteId, font.id)
      await loadSiteFonts(c)
    } catch (err) {
      setError(message(err, 'Couldn’t take it off the list.'))
    }
  }

  return (
    <Dialog title="Your fonts" onClose={close}>
      <div className="space-y-4 p-4 text-sm">
        <p className="text-xs leading-relaxed text-zinc-400">
          Fonts you have a licence for, set in every story of this magazine and on its readers’ pages. Each one is
          served from Gummfit, so your licence has to allow use on a website (a web or app licence).
        </p>
        {error && <p role="alert" className="rounded-md bg-red-500/10 p-2 text-xs text-red-300">{error}</p>}
        <section aria-label="Add a font" className="space-y-2 rounded-lg border border-zinc-800 p-3">
          <input ref={input} type="file" accept={ACCEPT} aria-label="Font file" onChange={(e) => pick(e.target.files?.[0] ?? null)}
            className="block w-full text-xs text-zinc-300 file:mr-3 file:rounded-md file:border-0 file:bg-zinc-800 file:px-3 file:py-1.5 file:text-zinc-100" />
          <p className="text-[11px] text-zinc-500">TTF, OTF, WOFF or WOFF2, up to 10 MB. Add each weight and italic of a family under the same name.</p>
          <label className="block text-xs text-zinc-400">Name
            <input value={name} maxLength={60} onChange={(e) => setName(e.target.value)} aria-label="Font name"
              className="mt-1 block w-full rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-sm text-zinc-100" />
          </label>
          <div className="flex items-center gap-3 text-xs text-zinc-400">
            <label>Weight{' '}
              <select value={weight} aria-label="Weight" onChange={(e) => setWeight(e.target.value ? Number(e.target.value) : '')}
                className="rounded-md border border-zinc-700 bg-zinc-950 px-1 py-1 text-zinc-100">
                <option value="">As the file says</option>
                {WEIGHTS.map((w) => <option key={w} value={w}>{w}</option>)}
              </select>
            </label>
            <label className="flex items-center gap-1"><input type="checkbox" checked={italic} onChange={(e) => setItalic(e.target.checked)} /> Italic</label>
          </div>
          <label className="flex items-start gap-2 text-xs text-zinc-300">
            <input type="checkbox" checked={licence} onChange={(e) => setLicence(e.target.checked)} className="mt-0.5" />
            <span>I hold a licence for this font that lets me use it on a website, and I may upload it here.</span>
          </label>
          <button type="button" disabled={!file || !name.trim() || !licence || busy} onClick={() => void upload()}
            className="flex items-center gap-2 rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-40">
            {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Add font
          </button>
        </section>
        <section aria-label="This magazine's fonts" className="space-y-2">
          {!groups.length && <p className="text-xs text-zinc-500">No fonts of your own yet.</p>}
          {groups.map((g) => (
            <div key={g.key} className="rounded-lg border border-zinc-800 p-3">
              <div className="flex items-center justify-between">
                <p className="text-sm text-zinc-100" style={{ fontFamily: `'${familyName(g.faces[0].sha)}', sans-serif` }}>{g.name}</p>
                <button type="button" onClick={() => void rename(g.key, g.name)} className="text-[11px] text-zinc-400 hover:text-white">Rename</button>
              </div>
              <ul className="mt-1 space-y-1">
                {g.faces.map((f) => (
                  <li key={f.id} className="flex items-center justify-between text-xs text-zinc-400">
                    <span>{f.weight}{f.italic ? ' italic' : ''}{f.filename ? ` · ${f.filename}` : ''}</span>
                    <button type="button" onClick={() => void remove(f)} className="text-[11px] text-zinc-500 hover:text-red-300"
                      title="Off this list; pages that set it keep it">Remove</button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </section>
      </div>
    </Dialog>
  )
}
