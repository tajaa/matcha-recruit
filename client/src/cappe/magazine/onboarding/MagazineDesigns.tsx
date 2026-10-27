import { useEffect, useMemo, useState } from 'react'
import { Check, ChevronLeft, ChevronRight, Loader2 } from 'lucide-react'
import { composeDoc } from '../../studio/compose/compose'
import { loadHarfBuzz, Shaper } from '../../studio/compose/shaper'
import { FaceBook, loadManifest } from '../../studio/fonts/faces'
import { browserWidth, FontLoader } from '../../studio/fonts/loader'
import { COLLECTIONS } from '../../studio/ui/add/collections'
import { PagePreview } from '../../studio/ui/add/PagePreview'
import type { Doc } from '../../studio/model/types'
import { magazineStarter } from './starter'

export default function MagazineDesigns({ name, selected, onSelect, onReady, disabled }: {
  name: string; selected: string; onSelect: (id: string) => void
  onReady: (doc: Doc | null) => void; disabled: boolean
}) {
  const [fonts, setFonts] = useState<FontLoader | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)
  const [page, setPage] = useState(0)
  useEffect(() => {
    let live = true
    ;(async () => {
      const [manifest, hb] = await Promise.all([loadManifest(), loadHarfBuzz()])
      const loader = new FontLoader(new FaceBook(manifest), new Shaper(hb, browserWidth))
      await Promise.all(COLLECTIONS.map((c) => loader.ensureDoc(c.doc)))
      if (live) setFonts(loader)
    })().catch((e) => { if (live) setError(e instanceof Error ? e.message : 'Could not load the designs.') })
    return () => { live = false }
  }, [retry])
  const covers = useMemo(() => fonts ? COLLECTIONS.map((c) => composeDoc(c.doc, fonts.measure, true).doc) : [], [fonts])
  const collection = COLLECTIONS.find((c) => c.id === selected) ?? COLLECTIONS[0]
  const draft = useMemo(() => fonts ? magazineStarter(collection.doc, name, fonts.measure) : null, [collection, name, fonts])
  useEffect(() => { onReady(draft) }, [draft, onReady])
  return <section aria-label="Choose your design" className="space-y-5">
    <div>
      <p className="text-xs uppercase tracking-[0.2em] text-zinc-500">02 / Art direction</p>
      <h2 className="mt-2 text-xl text-zinc-100">Choose your first edition.</h2>
      <p className="mt-2 text-sm leading-relaxed text-zinc-400">Ten coordinated pages, from cover to credits. Every word, frame and colour is yours to edit.</p>
    </div>
    {error ? <div role="alert" className="space-y-2 text-sm text-red-300"><p>{error}</p>
      <button type="button" className="underline" onClick={() => { setError(null); setRetry((n) => n + 1) }}>Reload designs</button>
    </div> : !fonts ? <p role="status" className="flex items-center gap-2 py-12 text-sm text-zinc-400"><Loader2 className="h-4 w-4 animate-spin" />Preparing your designs…</p> : <>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {COLLECTIONS.map((c, i) => <button key={c.id} type="button" aria-pressed={selected === c.id} disabled={disabled}
          onClick={() => { onSelect(c.id); setPage(0) }} aria-label={`Choose ${c.name}`}
          className={`flex min-w-0 flex-col items-center gap-3 rounded-lg border px-2 py-3 text-left transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400 ${selected === c.id ? 'border-emerald-500 bg-emerald-500/5' : 'border-zinc-800 hover:border-zinc-500'}`}>
          <PagePreview doc={covers[i]} faces={fonts.book} width={100} sample={c.id} />
          <span className="flex w-full items-center justify-between text-xs text-zinc-200">{c.name}{selected === c.id && <Check className="h-3 w-3 text-emerald-400" />}</span>
        </button>)}
      </div>
      {draft && <div className="grid items-center gap-6 rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 sm:grid-cols-[auto_1fr] sm:p-6">
        <div className="mx-auto"><PagePreview doc={draft} faces={fonts.book} page={page} width={228} sample={collection.id} /></div>
        <div className="space-y-4">
          <div><p className="text-xs uppercase tracking-widest text-zinc-500">{collection.direction}</p>
            <h3 className="mt-2 text-xl text-zinc-100">{collection.name}</h3>
            <p className="mt-2 text-sm leading-relaxed text-zinc-400">{collection.description}</p></div>
          <p className="text-xs leading-relaxed text-zinc-500">{collection.fonts}</p>
          <div className="flex items-center gap-3" aria-label="Browse design pages">
            <button type="button" aria-label="Previous design page" disabled={page === 0} onClick={() => setPage((n) => n - 1)} className="rounded border border-zinc-700 p-2 text-zinc-300 disabled:opacity-30"><ChevronLeft className="h-4 w-4" /></button>
            <p aria-live="polite" className="text-xs text-zinc-400">{page + 1} / {draft.pages.length} · {collection.pages[page]}</p>
            <button type="button" aria-label="Next design page" disabled={page === draft.pages.length - 1} onClick={() => setPage((n) => n + 1)} className="rounded border border-zinc-700 p-2 text-zinc-300 disabled:opacity-30"><ChevronRight className="h-4 w-4" /></button>
          </div>
          <p className="text-xs leading-relaxed text-zinc-500">Sample photos show the design. Your draft starts with empty picture frames, ready for your own images.</p>
        </div>
      </div>}
    </>}
  </section>
}
