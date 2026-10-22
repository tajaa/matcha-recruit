import { useState } from 'react'
import { Check, Loader2, Search, Wand2, X } from 'lucide-react'
import { cappeApi } from '../../api'
import { ui } from '../../components/ui'
import type { CappeAsset, CappeStoryAssist, StoryAssistAction, StoryBlock } from '../../types'
import { STOCK_SOURCES, thumbUrl } from '../library/assets'
import { textPreview } from './blocks'

type Term = NonNullable<CappeStoryAssist['terms']>[number]
type Headline = NonNullable<CappeStoryAssist['headlines']>[number]
type Draft = NonNullable<CappeStoryAssist['draft']>

const TABS: { key: StoryAssistAction; label: string; hint: string }[] = [
  { key: 'draft', label: 'Draft', hint: 'A first draft from your notes and the pictures in this story.' },
  { key: 'headlines', label: 'Headlines', hint: 'Five headline, dek and kicker sets, each a different angle.' },
  { key: 'captions', label: 'Captions', hint: 'A caption and alt text for each picture in the story.' },
  { key: 'tighten', label: 'Tighten', hint: 'One passage, shorter and sharper, in your words.' },
  { key: 'search_terms', label: 'Find pictures', hint: 'Searches of the free archives that would suit this story.' },
]

/**
 * The story editor's Assist: fixed writing actions on Claude. Each one
 * returns a proposal shown here; nothing changes in the story until the
 * writer applies it (and nothing is saved until they save). The server never
 * invents facts or quotes; where a fact is missing a draft says "[check: …]".
 */
export default function AssistPanel({ siteId, postId, title, excerpt, blocks, assets, onHeadline, onCaption,
  onAlt, onTighten, onDraft, onFind, onClose }: {
  siteId: string
  postId: string
  title: string
  excerpt: string
  blocks: StoryBlock[]
  assets: Map<string, CappeAsset>
  onHeadline: (h: Headline) => void
  onCaption: (assetId: string, caption: string) => void
  onAlt: (asset: CappeAsset) => void
  onTighten: (block: number, md: string) => void
  onDraft: (draft: Draft) => void
  onFind: (term: Term) => void
  onClose: () => void
}) {
  const [tab, setTab] = useState<StoryAssistAction>('headlines')
  const [notes, setNotes] = useState('')
  const [block, setBlock] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [results, setResults] = useState<Partial<Record<StoryAssistAction, CappeStoryAssist>>>({})
  const [used, setUsed] = useState<Set<string>>(new Set())
  // The words Tighten was asked about: the passage it replaces is found by
  // them, not by its place (blocks can move while the answer is read).
  const [tightened, setTightened] = useState<string | null>(null)

  const textBlocks = blocks.map((b, i) => ({ b, i })).filter(({ b }) => b.type === 'text' && b.md.trim())
  const chosenBlock = block ?? textBlocks[0]?.i ?? null
  const result = results[tab]

  const ask = async () => {
    setBusy(true)
    setError(null)
    const body: Record<string, unknown> = { action: tab, content: { blocks }, title, excerpt }
    if (tab === 'draft') body.notes = notes
    if (tab === 'tighten') body.block = chosenBlock
    const asked = tab === 'tighten' && chosenBlock !== null ? (blocks[chosenBlock] as Extract<StoryBlock, { type: 'text' }>).md : null
    try {
      const res = await cappeApi.post<CappeStoryAssist>(`/sites/${siteId}/posts/${postId}/assist`, body)
      if (tab === 'tighten') setTightened(asked)
      setResults((r) => ({ ...r, [tab]: res }))
      setUsed(new Set())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Writing help didn’t answer this time. Try again.')
    } finally {
      setBusy(false)
    }
  }

  const mark = (key: string) => setUsed((s) => new Set(s).add(key))

  const applyCaption = async (c: NonNullable<CappeStoryAssist['captions']>[number]) => {
    if (c.caption) onCaption(c.asset_id, c.caption)
    const asset = assets.get(c.asset_id)
    if (c.alt && asset && !asset.alt) {
      try {
        onAlt(await cappeApi.patch<CappeAsset>(`/sites/${siteId}/assets/${asset.id}`, { alt: c.alt }))
      } catch { /* the caption is in; alt text can be written in the library */ }
    }
    mark(c.asset_id)
  }

  const applyDraft = (draft: Draft) => {
    // Words or pictures anywhere (a photo essay may have no text yet).
    const hasWork = blocks.some((b) => /"(md|a_md|q|text|caption|asset_id)":"\s*\S/.test(JSON.stringify(b)))
    if (hasWork && !window.confirm('Replace the story’s blocks with this draft? You can still leave without saving.')) return
    onDraft(draft)
    mark('draft')
  }

  const tightenAt = tightened === null ? -1
    : blocks.findIndex((b) => b.type === 'text' && b.md === tightened)

  const canAsk = tab === 'tighten' ? chosenBlock !== null : tab === 'draft' ? notes.trim().length > 0 || blocks.length > 0 : true

  return (
    // Its fields keep the browser's own undo, not the story's.
    <section className={`${ui.card} space-y-3 p-4`} aria-label="Assist" data-native-undo>
      <div className="flex items-center justify-between gap-2">
        <h2 className="inline-flex items-center gap-2 text-sm font-medium text-zinc-100"><Wand2 className="h-4 w-4" /> Assist</h2>
        <button type="button" onClick={onClose} className="text-zinc-500 hover:text-zinc-300" aria-label="Close Assist"><X className="h-4 w-4" /></button>
      </div>
      <div className="flex flex-wrap gap-1" role="tablist" aria-label="Assist action">
        {TABS.map((t) => (
          <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} onClick={() => { setTab(t.key); setError(null) }}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium ${tab === t.key ? 'bg-emerald-500/15 text-emerald-400' : 'text-zinc-400 hover:bg-zinc-800'}`}>
            {t.label}
          </button>
        ))}
      </div>
      <p className="text-xs text-zinc-500">{TABS.find((t) => t.key === tab)?.hint} Proposals only: read them before you use them.</p>

      {tab === 'draft' && (
        <label className="block">
          <span className={ui.label}>Your notes</span>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={4} maxLength={2000} className={ui.input}
            placeholder="What happened, who you met, what you saw. Quotes you want used, word for word." />
        </label>
      )}
      {tab === 'tighten' && (
        textBlocks.length ? (
          <label className="block">
            <span className={ui.label}>Passage</span>
            <select value={chosenBlock ?? ''} onChange={(e) => setBlock(Number(e.target.value))} className={ui.input}>
              {textBlocks.map(({ b, i }) => (
                <option key={i} value={i}>Block {i + 1}: {b.type === 'text' ? textPreview(b.md) : ''}</option>
              ))}
            </select>
          </label>
        ) : <p className="text-sm text-zinc-400">Write a text block first, then tighten it here.</p>
      )}

      <button type="button" className={ui.btnPrimary} disabled={busy || !canAsk} onClick={ask}>
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
        {busy ? 'Writing…' : result ? 'Try again' : 'Ask'}
      </button>
      {error && <p role="alert" className="text-sm text-red-400">{error}</p>}

      {result?.headlines && (
        <ul className="space-y-2" aria-label="Headlines">
          {result.headlines.map((h, n) => (
            <li key={n} className="rounded-lg border border-zinc-800 p-3">
              {h.kicker && <p className="text-[11px] uppercase tracking-wide text-zinc-500">{h.kicker}</p>}
              <p className="font-medium text-zinc-100">{h.title}</p>
              {h.dek && <p className="text-sm text-zinc-400">{h.dek}</p>}
              <button type="button" className={`${ui.btnGhost} mt-2`} onClick={() => { onHeadline(h); mark(`h${n}`) }}>
                {used.has(`h${n}`) ? <><Check className="h-4 w-4" /> Used</> : 'Use this'}
              </button>
            </li>
          ))}
        </ul>
      )}

      {result?.captions && (
        <ul className="space-y-2" aria-label="Captions">
          {result.captions.map((c) => {
            const asset = assets.get(c.asset_id)
            return (
              <li key={c.asset_id} className="flex gap-3 rounded-lg border border-zinc-800 p-3">
                {asset && <img src={thumbUrl(asset)} alt="" className="h-16 w-20 shrink-0 rounded object-cover" />}
                <div className="min-w-0 flex-1 space-y-1">
                  <p className="text-sm text-zinc-100">{c.caption}</p>
                  {c.alt && <p className="text-xs text-zinc-500">Alt text: {c.alt}{asset?.alt ? ' (this picture already has alt text, kept as is)' : ''}</p>}
                  <button type="button" className={ui.btnGhost} onClick={() => void applyCaption(c)}>
                    {used.has(c.asset_id) ? <><Check className="h-4 w-4" /> Used</> : 'Use this'}
                  </button>
                </div>
              </li>
            )
          })}
        </ul>
      )}

      {result?.md !== undefined && tab === 'tighten' && tightenAt === -1 && !used.has('tighten') && (
        <p className="text-sm text-zinc-400">That passage has changed since you asked. Ask again to tighten it as it is now.</p>
      )}
      {result?.md !== undefined && tightenAt !== -1 && (
        <div className="space-y-2">
          <div className="grid gap-3 md:grid-cols-2">
            <div>
              <p className={ui.label}>Now</p>
              <p className="whitespace-pre-wrap rounded-lg bg-zinc-950 p-3 text-sm text-zinc-400">
                {(blocks[tightenAt] as Extract<StoryBlock, { type: 'text' }>).md}
              </p>
            </div>
            <div>
              <p className={ui.label}>Tighter</p>
              <p className="whitespace-pre-wrap rounded-lg bg-zinc-950 p-3 text-sm text-zinc-100">{result.md}</p>
            </div>
          </div>
          <button type="button" className={ui.btnGhost} onClick={() => { onTighten(tightenAt, result.md!); setTightened(result.md!); mark('tighten') }}>
            {used.has('tighten') ? <><Check className="h-4 w-4" /> Replaced</> : 'Replace the passage'}
          </button>
        </div>
      )}

      {result?.terms && (
        <ul className="space-y-1" aria-label="Searches">
          {result.terms.map((t, n) => (
            <li key={n} className="flex items-center gap-2 text-sm">
              <span className="w-24 shrink-0 text-xs text-zinc-500">{STOCK_SOURCES.find((s) => s.key === t.source)?.label}</span>
              <span className="flex-1 text-zinc-200">{t.query}</span>
              <button type="button" className={ui.btnGhost} onClick={() => onFind(t)}><Search className="h-4 w-4" /> Search</button>
            </li>
          ))}
        </ul>
      )}

      {result?.draft && (
        <div className="space-y-2 rounded-lg border border-zinc-800 p-3">
          {result.draft.kicker && <p className="text-[11px] uppercase tracking-wide text-zinc-500">{result.draft.kicker}</p>}
          <p className="font-medium text-zinc-100">{result.draft.title || title}</p>
          {result.draft.excerpt && <p className="text-sm text-zinc-400">{result.draft.excerpt}</p>}
          <ol className="list-decimal space-y-1 pl-5 text-sm text-zinc-300">
            {result.draft.content.blocks.map((b, n) => (
              <li key={n}>{b.type === 'text' ? textPreview(b.md, 14) : b.type === 'quote' ? `“${b.text}”` : b.type}</li>
            ))}
          </ol>
          {JSON.stringify(result.draft).includes('[check:') && (
            <p className="text-xs text-amber-300">Fill in each [check: …] before you publish.</p>
          )}
          <button type="button" className={ui.btnPrimary} onClick={() => applyDraft(result.draft!)}>
            {used.has('draft') ? <><Check className="h-4 w-4" /> In the editor</> : 'Use this draft'}
          </button>
        </div>
      )}
    </section>
  )
}
