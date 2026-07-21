import { useEffect, useRef, useState } from 'react'
import { cappeApi } from '../../../api'
import type { CappeBlock } from '../../../types'
import { applyMerlinOps, type MerlinDesignSchema, type MerlinOp, type MerlinOpResult } from './merlinOps'

export type MerlinTier = 'lite' | 'regular'

/** Mirrors MODEL_TIERS in server/app/cappe/services/merlin_catalog.py.
 *  `premium` marks the tiers that need a Pro/Business plan — the server
 *  clamps regardless, this only drives the picker UI. */
export const MERLIN_TIERS: { id: MerlinTier; label: string; hint: string; premium: boolean }[] = [
  { id: 'lite', label: 'Lite', hint: 'Fastest, best for small edits', premium: false },
  { id: 'regular', label: 'Regular', hint: 'Balanced — good for most changes', premium: true },
]

export type MerlinMessage = {
  role: 'user' | 'assistant'
  content: string
  results?: MerlinOpResult[]
  tier?: MerlinTier
  /** True when the turn changed nothing. The panel renders an explicit "no
   *  changes" marker for these — the model's prose has claimed effects it
   *  never produced ("I've enabled the hero shimmer"), so the UI states the
   *  ground truth rather than trusting the sentence. */
  noChanges?: boolean
}

type MerlinChatResponse = {
  message: string
  ops: MerlinOp[]
  rejected: { op: unknown; reason: string }[]
  tier?: MerlinTier
}

const HISTORY_TURNS = 10
const TIER_KEY = 'cappe:merlin-tier'
const TRANSCRIPT_MAX = 30

const transcriptKey = (siteId?: string, pageId?: string): string | null =>
  siteId && pageId ? `cappe:merlin-chat:${siteId}:${pageId}` : null

/** Merlin chat: client-held transcript (lost on reload — acceptable for v1),
 *  resent each turn capped at HISTORY_TURNS. Applying is a single-shot
 *  request/response (no SSE — see the plan doc): the panel shows a spinner
 *  for the ~2-5s round trip, then the whole op batch applies at once via
 *  `onApply`, so useEditorHistory records one undo step per turn.
 *
 *  `getSnapshot` MUST read live state (a ref in the caller, not a render-time
 *  closure): ops are validated against the pre-flight snapshot but applied to
 *  whatever the page looks like when the response lands ~2-5s later. Applying
 *  to the stale array instead silently reverted every edit the user made
 *  during the request. Ops are id-addressed and applyMerlinOps skips ids it
 *  can't resolve, so a block deleted mid-flight degrades to a "Skipped" chip. */
export function useMerlin(
  siteId: string | undefined,
  pageId: string | undefined,
  /** Also carries `selectedBlock` — the block the user has selected in the
   *  editor, so "this section" resolves instead of being guessed at. */
  getSnapshot: () => {
    blocks: CappeBlock[]
    theme: Record<string, unknown>
    selectedBlock?: string | null
  },
  onApply: (next: {
    blocks: CappeBlock[]
    theme: Record<string, unknown>
    blocksChanged: boolean
    themeChanged: boolean
  }) => void,
) {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<MerlinMessage[]>([])
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Lite by default; persisted across pages/sessions like werk's 'mw-model'.
  // Validated against the current tier list, so a value saved before a tier
  // was retired (e.g. the old 'pro') falls back instead of being sent on.
  const [tier, setTierState] = useState<MerlinTier>(() => {
    const saved = localStorage.getItem(TIER_KEY)
    return MERLIN_TIERS.some((t) => t.id === saved) ? (saved as MerlinTier) : 'lite'
  })
  const setTier = (t: MerlinTier) => {
    setTierState(t)
    try { localStorage.setItem(TIER_KEY, t) } catch { /* ignore quota */ }
  }

  // Live siteId/pageId, read by both the in-flight check in `send` (below)
  // and the persist effect below — both need a ref because `send` closes
  // over a stale `pageId` otherwise, and the persist effect must NOT list
  // pageId/siteId as dependencies (see that effect's comment for why).
  const siteIdRef = useRef(siteId)
  siteIdRef.current = siteId
  const pageIdRef = useRef(pageId)
  pageIdRef.current = pageId

  // PageEditor is NOT remounted when the route's :pageId changes (no `key` on
  // the route), so without this the transcript — and its ops_summary context —
  // would bleed from one page into the next. Restores that page's own saved
  // transcript instead of always clearing (lost-on-reload was acceptable for
  // v1; losing it on every navigation was needlessly worse).
  // Also clear `sending`: an in-flight turn (esp. a slow image generation)
  // belongs to the page it was started on — its apply is pageId-guarded — so
  // don't leave the destination page's panel spinning + re-entry-locked.
  useEffect(() => {
    const key = transcriptKey(siteId, pageId)
    let restored: MerlinMessage[] = []
    if (key) {
      try {
        const raw = localStorage.getItem(key)
        const parsed = raw ? JSON.parse(raw) : null
        // Guard the shape, not just JSON.parse: a truncated write, a devtools
        // edit, or a future format change can leave non-array JSON (null,
        // `{}`, a bare string) in the slot — feeding that to setMessages
        // crashes the panel's `messages.length` read on the very next render.
        if (Array.isArray(parsed)) restored = parsed
      } catch { /* corrupt entry — start fresh rather than throw */ }
    }
    setMessages(restored)
    setError(null)
    setSending(false)
  }, [siteId, pageId])

  // Persists on every turn, capped so a long-running session doesn't grow the
  // localStorage entry unboundedly. An empty transcript (fresh page, or after
  // clearChat) removes the key rather than storing `"[]"`.
  //
  // Deps are `[messages]` ONLY — siteId/pageId are read from refs instead.
  // On navigation, the load effect above and this one both re-run in the
  // same commit while `messages` still holds the OUTGOING page's transcript
  // (setMessages from the load effect hasn't applied yet); if this effect
  // also depended on siteId/pageId it would re-fire in that same commit and
  // write the outgoing page's messages under the incoming page's key. Firing
  // only on an actual `messages` change means this effect doesn't run again
  // until the load effect's setMessages has landed — by which point the refs
  // already agree with the transcript being persisted.
  useEffect(() => {
    const key = transcriptKey(siteIdRef.current, pageIdRef.current)
    if (!key) return
    try {
      if (messages.length) localStorage.setItem(key, JSON.stringify(messages.slice(-TRANSCRIPT_MAX)))
      else localStorage.removeItem(key)
    } catch { /* ignore quota */ }
  }, [messages])

  const clearChat = () => setMessages([])

  // Fetched once and cached for the component's lifetime: the registry it
  // reflects only changes on a deploy. A failed fetch (offline, cold start)
  // just leaves this null — applyMerlinOps falls back to trusting the
  // server's own validation, today's behavior.
  const schemaRef = useRef<MerlinDesignSchema | null>(null)
  useEffect(() => {
    let cancelled = false
    cappeApi.get<MerlinDesignSchema>('/merlin/schema')
      .then((s) => { if (!cancelled) schemaRef.current = s })
      .catch(() => { /* degrade to unvalidated apply */ })
    return () => { cancelled = true }
  }, [])

  // Execute generate_image ops sequentially: generate via the endpoint, then
  // apply the returned URL as a follow-up set_field to LIVE state (a second
  // onApply → its own undo step). Each result is reported as an assistant note.
  // Failures (quota 429, model 502, navigation) degrade to a note, never throw.
  const runImageOps = async (
    sid: string,
    ops: Extract<MerlinOp, { op: 'generate_image' }>[],
    sentForPageId: string,
  ) => {
    for (const g of ops) {
      try {
        const gen = await cappeApi.post<{ url: string }>(
          `/sites/${sid}/generate-image`,
          { prompt: g.prompt, aspect_ratio: g.aspect || '16:9' },
        )
        if (sentForPageId !== pageIdRef.current) return
        const cur = getSnapshot()
        const applied = applyMerlinOps(cur.blocks, cur.theme, [
          { op: 'set_field', block: g.block, path: g.field, value: gen.url },
        ])
        const changed = applied.blocks !== cur.blocks
        if (changed) {
          onApply({ blocks: applied.blocks, theme: applied.theme, blocksChanged: true, themeChanged: false })
        }
        setMessages((m) => [...m, {
          role: 'assistant',
          content: changed ? 'Generated and placed the image.' : 'Generated the image, but its target section is gone.',
          results: [{ ok: changed, summary: changed ? `Image → ${g.field}` : 'Target section not found' }],
          noChanges: !changed,
        }])
      } catch (e) {
        // Same navigation guard as the success path — don't drop a failure note
        // into a page the user navigated to during the ~10-30s generation.
        if (sentForPageId !== pageIdRef.current) return
        const msg = e instanceof Error ? e.message : 'Image generation failed'
        setMessages((m) => [...m, {
          role: 'assistant', content: `Image generation failed: ${msg}`,
          results: [{ ok: false, summary: 'Generation failed' }], noChanges: true,
        }])
      }
    }
  }

  const send = async (text: string) => {
    const trimmed = text.trim()
    if (!siteId || !pageId || !trimmed || sending) return
    setSending(true)
    setError(null)
    setMessages((m) => [...m, { role: 'user', content: trimmed }])
    const sentForPageId = pageId

    try {
      const { blocks, theme, selectedBlock } = getSnapshot()
      const snapshotBlocks = blocks.map((b) => {
        const { _k, ...rest } = b
        return { ...rest, id: _k }
      })
      const history = messages.slice(-HISTORY_TURNS).map((m) => ({
        role: m.role,
        content: m.content,
        ops_summary: m.results?.map((r) => r.summary).join('; '),
      }))

      const res = await cappeApi.post<MerlinChatResponse>(`/sites/${siteId}/merlin/chat`, {
        page_id: pageId,
        message: trimmed,
        history,
        blocks: snapshotBlocks,
        theme,
        model_tier: tier,
        selected_block: selectedBlock ?? null,
      })

      // Navigated to a different page while in flight — applying now would
      // overwrite THAT page's content with this one's blocks.
      if (sentForPageId !== pageIdRef.current) return

      // generate_image ops are server-validated but CLIENT-executed: generation
      // is a slow async round-trip and applyMerlinOps is a synchronous fold, so
      // they're split out and handled after the sync ops land.
      const allOps = res.ops || []
      const genOps = allOps.filter(
        (o): o is Extract<MerlinOp, { op: 'generate_image' }> => o.op === 'generate_image',
      )
      const syncOps = allOps.filter((o) => o.op !== 'generate_image')

      // Re-read: apply to live state, not the pre-flight snapshot.
      const cur = getSnapshot()
      const applied = applyMerlinOps(cur.blocks, cur.theme, syncOps, schemaRef.current ?? undefined)
      const blocksChanged = applied.blocks !== cur.blocks
      const themeChanged = applied.theme !== cur.theme
      if (blocksChanged || themeChanged) {
        onApply({ blocks: applied.blocks, theme: applied.theme, blocksChanged, themeChanged })
      }
      const skippedFromServer = (res.rejected || []).map((r) => ({ ok: false, summary: r.reason }))
      const results = [...applied.results, ...skippedFromServer]
      setMessages((m) => [...m, {
        role: 'assistant', content: res.message, tier: res.tier, results,
        // An image is still generating — don't declare "no changes" yet.
        noChanges: genOps.length === 0 && !results.some((r) => r.ok),
      }])

      // Kept inside `send`'s try so `sending` (and the panel spinner) stays true
      // across the slow generation; a per-image assistant note reports each one.
      // `block` may be a same-turn add_block's temp id — remap through the
      // map applying the sync ops just built, same as applyMerlinOps does
      // internally for every other op that can target one.
      if (genOps.length) {
        const remapped = genOps.map((g) => ({ ...g, block: applied.tempIdMap[g.block] ?? g.block }))
        await runImageOps(siteId, remapped, sentForPageId)
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Merlin failed to respond'
      setError(msg)
      setMessages((m) => [...m, { role: 'assistant', content: `Something went wrong: ${msg}` }])
    } finally {
      setSending(false)
    }
  }

  return { open, setOpen, messages, send, sending, error, tier, setTier, clearChat }
}
