import { useEffect, useRef, useState } from 'react'
import { cappeApi } from '../../../api'
import type { CappeBlock } from '../../../types'
import { applyMerlinOps, type MerlinOp, type MerlinOpResult } from './merlinOps'

export type MerlinTier = 'lite' | 'regular' | 'pro'

/** Mirrors MODEL_TIERS in server/app/cappe/services/merlin_catalog.py.
 *  `premium` marks the tiers that need a Pro/Business plan — the server
 *  clamps regardless, this only drives the picker UI. */
export const MERLIN_TIERS: { id: MerlinTier; label: string; hint: string; premium: boolean }[] = [
  { id: 'lite', label: 'Lite', hint: 'Fastest, best for small edits', premium: false },
  { id: 'regular', label: 'Regular', hint: 'Balanced — good for most changes', premium: true },
  { id: 'pro', label: 'Pro', hint: 'Most capable, slowest', premium: true },
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
  const [tier, setTierState] = useState<MerlinTier>(() => {
    const saved = localStorage.getItem(TIER_KEY)
    return saved === 'regular' || saved === 'pro' ? saved : 'lite'
  })
  const setTier = (t: MerlinTier) => {
    setTierState(t)
    try { localStorage.setItem(TIER_KEY, t) } catch { /* ignore quota */ }
  }

  // PageEditor is NOT remounted when the route's :pageId changes (no `key` on
  // the route), so without this the transcript — and its ops_summary context —
  // would bleed from one page into the next.
  useEffect(() => { setMessages([]); setError(null) }, [pageId])

  // Live pageId for the in-flight check in `send`. It MUST be a ref: `send` is
  // recreated each render, so an in-flight call and the `pageId` param it can
  // see are the same closure binding — comparing them is always false, and the
  // navigation guard silently never fires.
  const pageIdRef = useRef(pageId)
  pageIdRef.current = pageId

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

      // Re-read: apply to live state, not the pre-flight snapshot.
      const cur = getSnapshot()
      const applied = applyMerlinOps(cur.blocks, cur.theme, res.ops || [])
      const blocksChanged = applied.blocks !== cur.blocks
      const themeChanged = applied.theme !== cur.theme
      if (blocksChanged || themeChanged) {
        onApply({ blocks: applied.blocks, theme: applied.theme, blocksChanged, themeChanged })
      }
      const skippedFromServer = (res.rejected || []).map((r) => ({ ok: false, summary: r.reason }))
      const results = [...applied.results, ...skippedFromServer]
      setMessages((m) => [...m, {
        role: 'assistant', content: res.message, tier: res.tier, results,
        noChanges: !results.some((r) => r.ok),
      }])
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Merlin failed to respond'
      setError(msg)
      setMessages((m) => [...m, { role: 'assistant', content: `Something went wrong: ${msg}` }])
    } finally {
      setSending(false)
    }
  }

  return { open, setOpen, messages, send, sending, error, tier, setTier }
}
