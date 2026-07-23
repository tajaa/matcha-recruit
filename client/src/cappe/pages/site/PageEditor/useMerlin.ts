import { useEffect, useRef, useState } from 'react'
import { cappeApi } from '../../../api'
import { postCappeSSE } from '../../../sse'
import type { CappeBlock } from '../../../types'
import { applyMerlinOps, type MerlinDesignSchema, type MerlinOp, type MerlinOpResult } from './merlinOps'

export type MerlinTier = 'lite' | 'regular' | 'max'
/** What the picker offers. 'auto' is not a model — the server resolves it per
 *  request (`services/merlin_router.py`) and reports which tier it chose. */
export type MerlinTierChoice = MerlinTier | 'auto'

/** Mirrors MODEL_TIERS in server/app/cappe/services/merlin_catalog.py.
 *  `premium` marks the tiers that need a Pro/Business plan — the server
 *  clamps regardless, this only drives the picker UI. Auto is listed first and
 *  is the default: picking between these is a question about model economics,
 *  not about the user's website. */
export const MERLIN_TIERS: { id: MerlinTierChoice; label: string; hint: string; premium: boolean }[] = [
  { id: 'auto', label: 'Auto', hint: 'Picks the right model for each request', premium: false },
  { id: 'lite', label: 'Lite', hint: 'Fastest, best for small edits', premium: false },
  { id: 'regular', label: 'Regular', hint: 'Balanced — good for most changes', premium: true },
  { id: 'max', label: 'Max', hint: 'Looks at the page as it edits — best for design work', premium: true },
]

export type MerlinMessage = {
  role: 'user' | 'assistant'
  content: string
  results?: MerlinOpResult[]
  tier?: MerlinTier
  /** True when Auto picked `tier` — the panel says "Auto → Max" so the user can
   *  see the router working rather than guessing whether it does anything. */
  routed?: boolean
  /** True when the turn changed nothing. The panel renders an explicit "no
   *  changes" marker for these — the model's prose has claimed effects it
   *  never produced ("I've enabled the hero shimmer"), so the UI states the
   *  ground truth rather than trusting the sentence. */
  noChanges?: boolean
  /** Server row id for an assistant message, used to report back which ops
   *  actually applied. Absent on optimistic/unrecorded messages. */
  id?: string
  /** The agent loop's trace for this turn — what it applied, what it rendered,
   *  what it looked at. Accumulates live while the turn streams. */
  steps?: MerlinStep[]
  /** Images the user attached to this message (place / style-reference /
   *  generation-input — Merlin infers which from the request text). */
  attachments?: MerlinAttachment[]
}

/** An uploaded image, referenced by URL — never inlined as bytes on the
 *  client. The server re-fetches from ITS OWN storage only (see
 *  merlin_attachments.py's SSRF guard), so this URL must come from the
 *  existing `/sites/{id}/upload` endpoint. */
export type MerlinAttachment = { url: string; mime: string }

/** One tool call in an agent turn. `results` mirrors the op chips; `image_url`
 *  is set on a `screenshot` step once the shot is stored. */
export type MerlinStep = {
  kind: 'ops' | 'screenshot' | 'inspect' | 'critique' | 'image'
  label: string
  results?: MerlinOpResult[]
  image_url?: string
}

export type MerlinConversation = {
  id: string
  title: string
  created_at: string
  updated_at: string
}

type MerlinChatResponse = {
  message: string
  ops: MerlinOp[]
  rejected: { op: unknown; reason: string }[]
  tier?: MerlinTier
  routed?: boolean
  conversation_id?: string | null
  message_id?: string | null
  steps?: MerlinStep[]
}

/** Frames from POST /sites/{id}/merlin/agent. The non-agentic tiers come back
 *  through the same stream as a single `result`, so there is one code path. */
type AgentFrame =
  | { type: 'status'; message: string }
  | { type: 'step'; kind: MerlinStep['kind']; label: string; results?: MerlinOpResult[]; image_url?: string }
  | { type: 'error'; message: string }
  | { type: 'result'; data: MerlinChatResponse }

type StoredMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  results?: MerlinOpResult[] | null
  tier?: MerlinTier | null
  steps?: MerlinStep[] | null
  attachments?: MerlinAttachment[] | null
}

const HISTORY_TURNS = 10
const TIER_KEY = 'cappe:merlin-tier'
const WIDTH_KEY = 'cappe:merlin-width'
const EXPANDED_KEY = 'cappe:merlin-expanded'
export const MERLIN_MIN_WIDTH = 320
export const MERLIN_MAX_WIDTH = 720
// Expanded ("pop out") width: a fraction of the viewport, capped — wide
// enough to feel like its own editor surface without ever fully covering
// the live preview it's editing alongside.
const EXPANDED_WIDTH_RATIO = 0.6
const EXPANDED_WIDTH_CAP = 900

/** Merlin chat: the transcript lives SERVER-side (migration zzzzcappe22), so a
 *  page can hold several named conversations and they survive a reload. The
 *  server reads history from the conversation row; `history` is still sent as
 *  a fallback for the first turn of a brand-new conversation. Applying is a
 *  single-shot request/response (no SSE — see the plan doc): the panel shows a
 *  spinner for the ~2-5s round trip, then the whole op batch applies at once
 *  via `onApply`, so useEditorHistory records one undo step per turn.
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
  // Live progress of an agent turn: the current status line and the tool-call
  // trace so far. Both clear when the turn's assistant message lands.
  const [status, setStatus] = useState<string | null>(null)
  const [liveSteps, setLiveSteps] = useState<MerlinStep[]>([])
  const abortRef = useRef<AbortController | null>(null)
  // Images attached to the NEXT message. Uploaded eagerly (through the same
  // /sites/{id}/upload the field picker uses) so `send` just sends URLs — the
  // server never accepts inline bytes, only its own storage's URLs.
  const [attachments, setAttachments] = useState<MerlinAttachment[]>([])
  const [attachmentUploading, setAttachmentUploading] = useState(false)
  const [attachmentError, setAttachmentError] = useState<string | null>(null)

  const addAttachment = async (file: File) => {
    if (!siteId || attachments.length >= 4) return
    setAttachmentUploading(true)
    setAttachmentError(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await cappeApi.upload<{ url: string }>(`/sites/${siteId}/upload`, fd)
      setAttachments((a) => [...a, { url: res.url, mime: file.type || 'image/png' }])
    } catch (e) {
      setAttachmentError(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setAttachmentUploading(false)
    }
  }
  /** Attach a URL that's already stored (an asset-library pick) instead of a
   *  fresh File — skips the upload round-trip since the object already lives
   *  in S3. The "edit them later" path: attach a past generation, ask for a
   *  variation, and the server turns it into a reference image. */
  const addAttachmentFromUrl = (url: string, mime = 'image/png') => {
    if (attachments.length >= 4) return
    setAttachments((a) => [...a, { url, mime }])
  }
  const removeAttachment = (idx: number) => setAttachments((a) => a.filter((_, i) => i !== idx))
  // Auto by default; persisted across pages/sessions like werk's 'mw-model'.
  // Validated against the current tier list, so a value saved before a tier
  // was retired (e.g. the old 'pro') falls back instead of being sent on.
  const [tier, setTierState] = useState<MerlinTierChoice>(() => {
    const saved = localStorage.getItem(TIER_KEY)
    return MERLIN_TIERS.some((t) => t.id === saved) ? (saved as MerlinTierChoice) : 'auto'
  })
  const setTier = (t: MerlinTierChoice) => {
    setTierState(t)
    try { localStorage.setItem(TIER_KEY, t) } catch { /* ignore quota */ }
  }

  // Panel width lives here rather than in the drawer because index.tsx needs it
  // for `reservedRight` (the canvas inspector is viewport-fixed and has to clamp
  // clear of the docked panel).
  const [dockedWidth, setDockedWidthState] = useState<number>(() => {
    const saved = Number(localStorage.getItem(WIDTH_KEY))
    return Number.isFinite(saved) && saved >= MERLIN_MIN_WIDTH && saved <= MERLIN_MAX_WIDTH
      ? saved
      : MERLIN_MIN_WIDTH
  })
  const clampWidth = (px: number) =>
    Math.min(MERLIN_MAX_WIDTH, Math.max(MERLIN_MIN_WIDTH, Math.round(px)))
  /** Update the live width without touching localStorage — for a drag in
   *  progress, where the panel rAF-throttles this but every intermediate
   *  value is still a full re-render (the message list, its screenshot
   *  thumbnails, and the canvas bridge's `reservedRight` all key off it). A
   *  localStorage write per call would add synchronous disk I/O on top of
   *  that for a value only the FINAL position needs persisted. */
  const setWidthLive = (px: number) => setDockedWidthState(clampWidth(px))
  /** Commit — persists to localStorage. Call once a drag ends. */
  const setWidth = (px: number) => {
    const clamped = clampWidth(px)
    setDockedWidthState(clamped)
    try { localStorage.setItem(WIDTH_KEY, String(clamped)) } catch { /* ignore quota */ }
  }

  // "Pop out" — widens the panel so it reads as its own editor surface
  // instead of a narrow sidebar, without detaching into a separate window
  // (a real window loses the live-preview + editor-state coupling that is
  // the whole point of Merlin acting directly on the page).
  const [expanded, setExpandedState] = useState<boolean>(
    () => localStorage.getItem(EXPANDED_KEY) === '1',
  )
  const setExpanded = (v: boolean) => {
    setExpandedState(v)
    try { localStorage.setItem(EXPANDED_KEY, v ? '1' : '0') } catch { /* ignore quota */ }
  }
  const [expandedWidth, setExpandedWidth] = useState(() =>
    Math.min(window.innerWidth * EXPANDED_WIDTH_RATIO, EXPANDED_WIDTH_CAP),
  )
  useEffect(() => {
    if (!expanded) return
    const onResize = () => setExpandedWidth(Math.min(window.innerWidth * EXPANDED_WIDTH_RATIO, EXPANDED_WIDTH_CAP))
    onResize()
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [expanded])
  // The EFFECTIVE width — what index.tsx's `reservedRight` and the drawer's
  // own `style={{ width }}` both read. Callers don't need to know docked vs.
  // expanded is two different numbers under the hood.
  const width = expanded ? expandedWidth : dockedWidth

  // Live siteId/pageId, read by both the in-flight check in `send` (below)
  // and the persist effect below — both need a ref because `send` closes
  // over a stale `pageId` otherwise, and the persist effect must NOT list
  // pageId/siteId as dependencies (see that effect's comment for why).
  const siteIdRef = useRef(siteId)
  siteIdRef.current = siteId
  const pageIdRef = useRef(pageId)
  pageIdRef.current = pageId

  // The conversation this panel is showing. `null` = a fresh one, opened
  // server-side by the first turn (which returns its id).
  const [conversationId, setConversationId] = useState<string | null>(null)
  const conversationIdRef = useRef<string | null>(null)
  conversationIdRef.current = conversationId
  const [conversations, setConversations] = useState<MerlinConversation[]>([])

  // Bumped every time the user SWITCHES which conversation the panel is
  // showing (open/new — not the auto-adopt of a fresh conversation's own id
  // inside `send`, below). A turn in flight for the conversation the user has
  // since navigated away from must not land its reply, ops or id-adoption in
  // whatever conversation is open when it resolves — unlike a page change,
  // switching conversations does NOT abort the in-flight request.
  const sessionRef = useRef(0)

  const refreshConversations = async (sid: string, pid: string) => {
    try {
      const list = await cappeApi.get<MerlinConversation[]>(
        `/sites/${sid}/pages/${pid}/merlin/conversations`,
      )
      if (sid === siteIdRef.current && pid === pageIdRef.current) setConversations(list)
    } catch { /* the panel still works without the history list */ }
  }

  const openConversation = async (id: string, opts?: { silent?: boolean }) => {
    sessionRef.current += 1
    if (!opts?.silent) setMessages([])
    setConversationId(id)
    setError(null)
    try {
      const detail = await cappeApi.get<{ id: string; messages: StoredMessage[] }>(
        `/merlin/conversations/${id}`,
      )
      // The user may have switched conversations again while this was in
      // flight — only paint if this is still the open one.
      if (conversationIdRef.current !== id) return
      setMessages(
        detail.messages.map((m) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          results: m.results ?? undefined,
          tier: m.tier ?? undefined,
          // Only claim "no changes" for a turn we have chips for — a message
          // whose results were never reported back is unknown, not empty.
          noChanges: m.role === 'assistant' && !!m.results && !m.results.some((r) => r.ok),
          steps: m.steps ?? undefined,
          attachments: m.attachments ?? undefined,
        })),
      )
    } catch {
      setError('Could not load that conversation.')
    }
  }

  /** Start a new conversation. The row is only created server-side on the
   *  first turn, so this is purely local state until then. */
  const newConversation = () => {
    sessionRef.current += 1
    setConversationId(null)
    setMessages([])
    setError(null)
  }

  const renameConversation = async (id: string, title: string) => {
    const trimmed = title.trim().slice(0, 120)
    if (!trimmed) return
    setConversations((c) => c.map((x) => (x.id === id ? { ...x, title: trimmed } : x)))
    try {
      await cappeApi.patch(`/merlin/conversations/${id}`, { title: trimmed })
    } catch {
      if (siteIdRef.current && pageIdRef.current) {
        void refreshConversations(siteIdRef.current, pageIdRef.current)
      }
    }
  }

  const deleteConversation = async (id: string) => {
    setConversations((c) => c.filter((x) => x.id !== id))
    if (conversationIdRef.current === id) newConversation()
    try {
      await cappeApi.delete(`/merlin/conversations/${id}`)
    } catch {
      if (siteIdRef.current && pageIdRef.current) {
        void refreshConversations(siteIdRef.current, pageIdRef.current)
      }
    }
  }

  // PageEditor is NOT remounted when the route's :pageId changes (no `key` on
  // the route), so without this the transcript — and its ops_summary context —
  // would bleed from one page into the next. Loads that page's conversation
  // list and opens the most recent one.
  // Also clear `sending`: an in-flight turn (esp. a slow image generation)
  // belongs to the page it was started on — its apply is pageId-guarded — so
  // don't leave the destination page's panel spinning + re-entry-locked.
  useEffect(() => {
    // An in-flight agent turn belongs to the page it was started on. Its apply
    // is pageId-guarded either way, but aborting stops the stream (and its
    // screenshots) rather than letting it run on invisibly.
    abortRef.current?.abort()
    abortRef.current = null
    setMessages([])
    setConversations([])
    setConversationId(null)
    setError(null)
    setStatus(null)
    setLiveSteps([])
    setAttachments([])
    setSending(false)
    if (!siteId || !pageId) return
    let cancelled = false
    void (async () => {
      try {
        const list = await cappeApi.get<MerlinConversation[]>(
          `/sites/${siteId}/pages/${pageId}/merlin/conversations`,
        )
        // Guard against a navigation landing between the fetch and its
        // resolution — the same reason `send` re-checks pageIdRef.
        if (cancelled || siteId !== siteIdRef.current || pageId !== pageIdRef.current) return
        setConversations(list)
        if (list.length) await openConversation(list[0].id, { silent: true })
      } catch { /* start fresh rather than block the panel */ }
    })()
    return () => { cancelled = true }
    // openConversation is redefined every render; listing it would refetch on
    // every render. siteId/pageId are the real inputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteId, pageId])

  // Fetched once and cached for the component's lifetime: the registry it
  // reflects only changes on a deploy. A failed fetch (offline, cold start)
  // just leaves this null — applyMerlinOps falls back to trusting the
  // server's own validation, today's behavior. Kept as BOTH a ref (read
  // synchronously inside `send`, below) and reactive state (`schema`, so the
  // panel's `/` command menu — block labels, section presets, theme presets —
  // re-renders once the fetch resolves instead of reading a stale null).
  const schemaRef = useRef<MerlinDesignSchema | null>(null)
  const [schema, setSchema] = useState<MerlinDesignSchema | null>(null)
  useEffect(() => {
    let cancelled = false
    cappeApi.get<MerlinDesignSchema>('/merlin/schema')
      .then((s) => { if (!cancelled) { schemaRef.current = s; setSchema(s) } })
      .catch(() => { /* degrade to unvalidated apply */ })
    return () => { cancelled = true }
  }, [])

  const reportResults = async (messageId: string, results: MerlinOpResult[]) => {
    try {
      await cappeApi.patch(`/merlin/messages/${messageId}/results`, { results })
    } catch { /* cosmetic — the chips just won't survive a reload */ }
  }

  /** One block a generated (or attached) image can be dropped onto: its own
   *  image field(s) (hero image, logo, …) plus — every block type, per
   *  `merlin_ops._v_set_design` — a background. Background is Pro-only
   *  (`_design` is stripped on save for free plans, same gate the design
   *  bag is behind everywhere else), so it's simply not offered when the
   *  target would silently vanish on Save. */
  const getImageTargets = (premium: boolean) => {
    const { blocks } = getSnapshot()
    const blockSchemas = schema?.blocks ?? {}
    return blocks
      .filter((b): b is CappeBlock & { _k: string } => typeof b._k === 'string')
      .map((b) => {
        const type = String(b.type)
        const spec = blockSchemas[type]
        const fields = Object.entries(spec?.fields ?? {})
          .filter(([, f]) => f.kind === 'image')
          .map(([field]) => ({
            field,
            label: field.replace(/([a-z])([A-Z])/g, '$1 $2').replace(/^./, (c) => c.toUpperCase()),
          }))
        return { blockId: b._k, blockLabel: spec?.label ?? type, fields, canBackground: premium }
      })
      .filter((g) => g.fields.length > 0 || g.canBackground)
  }

  /** Apply an already-generated (or attached) image URL to a field or a
   *  background — the "Apply to…" menu's action. Synchronous fold against
   *  LIVE state, same one-undo-step contract as every other apply here. */
  const applyImageTo = (url: string, target: { block: string; field: string } | { block: string; background: true }) => {
    const cur = getSnapshot()
    const ops: MerlinOp[] = 'field' in target
      ? [{ op: 'set_field', block: target.block, path: target.field, value: url }]
      : [
          { op: 'set_design', block: target.block, group: 'bg', key: 'type', value: 'image' },
          { op: 'set_design', block: target.block, group: 'bg', key: 'image', value: url },
        ]
    const applied = applyMerlinOps(cur.blocks, cur.theme, ops, schemaRef.current ?? undefined)
    const changed = applied.blocks !== cur.blocks
    if (changed) {
      onApply({ blocks: applied.blocks, theme: applied.theme, blocksChanged: true, themeChanged: false })
    }
    setMessages((m) => [...m, {
      role: 'assistant',
      content: changed ? 'Applied the image.' : "Couldn't apply — that section is gone.",
      results: applied.results,
      noChanges: !applied.results.some((r) => r.ok),
    }])
  }

  // Execute generate_image ops sequentially: generate via the endpoint, then
  // apply the returned URL as a follow-up set_field to LIVE state (a second
  // onApply → its own undo step). Each result is reported as an assistant note.
  // Failures (quota 429, model 502, navigation) degrade to a note, never throw.
  const runImageOps = async (
    sid: string,
    ops: Extract<MerlinOp, { op: 'generate_image' }>[],
    sentForPageId: string,
    sentSession: number,
  ) => {
    for (const g of ops) {
      try {
        const gen = await cappeApi.post<{ url: string }>(
          `/sites/${sid}/generate-image`,
          { prompt: g.prompt, aspect_ratio: g.aspect || '16:9', image_size: g.image_size || '2K' },
        )
        if (sentForPageId !== pageIdRef.current || sentSession !== sessionRef.current) return
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
        // Same navigation/conversation guard as the success path — don't drop
        // a failure note into a page or conversation the user left during the
        // ~10-30s generation.
        if (sentForPageId !== pageIdRef.current || sentSession !== sessionRef.current) return
        const msg = e instanceof Error ? e.message : 'Image generation failed'
        setMessages((m) => [...m, {
          role: 'assistant', content: `Image generation failed: ${msg}`,
          results: [{ ok: false, summary: 'Generation failed' }], noChanges: true,
        }])
      }
    }
  }

  /** Direct generation from the wizard — bypasses the agent loop entirely
   *  (no Gemini reasoning about placement; the user already specified style/
   *  mood/aspect/quality themselves). POSTs straight to `/generate-image` —
   *  the server reshapes prompt+style+mood into the actual Gemini prompt
   *  (`image_prompting.build_image_prompt`) — shows the model/size as the
   *  live status line (same slot the agent loop's status frames use), and
   *  lands the result as an assistant message carrying an `image` step, so
   *  the existing thumbnail + "Apply to…" menu (and drag-to-section) handle
   *  placement. Nothing is auto-applied to a section — that was the
   *  complaint this replaces (an agent turn placing a generated image
   *  wherever it guessed, when nothing was selected). */
  const generateImage = async (opts: {
    prompt: string
    style?: string
    mood?: string
    aspect?: string
    size?: string
  }) => {
    if (!siteId || sending) return
    const size = opts.size || '2K'
    const sentForPageId = pageIdRef.current
    const sentSession = sessionRef.current
    setSending(true)
    setError(null)
    setStatus(`Generating image — gemini-3.1-flash-image · ${size}…`)
    setLiveSteps([])
    setMessages((m) => [...m, { role: 'user', content: `Generate an image: ${opts.prompt}` }])
    try {
      const gen = await cappeApi.post<{ url: string }>(
        `/sites/${siteId}/generate-image`,
        {
          prompt: opts.prompt, aspect_ratio: opts.aspect || '16:9', image_size: size,
          style: opts.style, mood: opts.mood,
        },
      )
      if (sentForPageId !== pageIdRef.current || sentSession !== sessionRef.current) return
      setMessages((m) => [...m, {
        role: 'assistant',
        content: `Generated a ${size} image. Use "Apply to…" below, or drag it onto a section in the preview to set it as the background.`,
        steps: [{ kind: 'image', label: `Generated image (${size})`, image_url: gen.url }],
      }])
    } catch (e) {
      if (sentForPageId !== pageIdRef.current || sentSession !== sessionRef.current) return
      const msg = e instanceof Error ? e.message : 'Image generation failed'
      setMessages((m) => [...m, {
        role: 'assistant', content: `Image generation failed: ${msg}`,
        results: [{ ok: false, summary: 'Generation failed' }], noChanges: true,
      }])
    } finally {
      if (sentForPageId === pageIdRef.current && sentSession === sessionRef.current) {
        setSending(false)
        setStatus(null)
      }
    }
  }

  const send = async (text: string) => {
    const trimmed = text.trim()
    if (!siteId || !pageId || !trimmed || sending) return
    const sentAttachments = attachments
    setSending(true)
    setError(null)
    setStatus(null)
    setLiveSteps([])
    setAttachments([])
    setMessages((m) => [
      ...m,
      { role: 'user', content: trimmed, attachments: sentAttachments.length ? sentAttachments : undefined },
    ])
    const sentForPageId = pageId
    const sentSession = sessionRef.current
    const abort = new AbortController()
    abortRef.current = abort

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

      // One endpoint for every tier: the SERVER decides whether this turn runs
      // the agent loop (premium + regular/max) or the single-shot path, and a
      // single-shot turn arrives as one `result` frame. Keeping the choice
      // server-side means plan/tier gating lives in one place.
      // Collected in a holder rather than plain `let`s: TS's control-flow
      // analysis can't see assignments made inside the frame callback, and
      // narrows a bare `let` to `never` after the null check below.
      const collected: { res: MerlinChatResponse | null; error: string | null } = {
        res: null, error: null,
      }
      const steps: MerlinStep[] = []

      await postCappeSSE(
        `/sites/${siteId}/merlin/agent`,
        {
          page_id: pageId,
          conversation_id: conversationIdRef.current,
          message: trimmed,
          history,
          blocks: snapshotBlocks,
          theme,
          model_tier: tier,
          selected_block: selectedBlock ?? null,
          attachments: sentAttachments,
        },
        (raw) => {
          const frame = raw as AgentFrame
          if (frame.type === 'status') setStatus(frame.message)
          else if (frame.type === 'step') {
            const { type: _t, ...step } = frame
            steps.push(step)
            setLiveSteps([...steps])
          } else if (frame.type === 'error') collected.error = frame.message
          else if (frame.type === 'result') collected.res = frame.data
        },
        { signal: abort.signal },
      )

      setStatus(null)
      const res = collected.res
      if (!res) {
        // The stream ended without a result — the error frame (if any) is the
        // explanation; otherwise the connection dropped.
        throw new Error(collected.error || 'Merlin failed to respond')
      }

      // The user switched to a different conversation (or started a new one)
      // while this turn was in flight. A page change aborts the request, but
      // switching conversations doesn't — so without this, a slow Max turn's
      // reply, ops and conversation_id land in whatever conversation happens
      // to be open when it resolves, not the one it was actually sent for.
      if (sessionRef.current !== sentSession) return

      if (collected.error) setError(collected.error)

      // Adopt the conversation the server opened for a first turn, and surface
      // it in the history list. Done before the navigation guard below: the row
      // exists regardless of where the user has navigated to.
      if (res.conversation_id && !conversationIdRef.current) {
        setConversationId(res.conversation_id)
        conversationIdRef.current = res.conversation_id
        void refreshConversations(siteId, sentForPageId)
      }

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
        role: 'assistant', id: res.message_id ?? undefined, content: res.message, tier: res.tier, results,
        routed: res.routed, steps: res.steps?.length ? res.steps : undefined,
        // An image is still generating — don't declare "no changes" yet.
        noChanges: genOps.length === 0 && !results.some((r) => r.ok),
      }])
      setLiveSteps([])

      // Only the client knows which ops actually landed (it applies to live
      // state, which may have drifted during the round trip), so it reports the
      // chips back for the stored transcript. Fire-and-forget: a failure costs
      // the chips on a reload, not the edit.
      if (res.message_id) void reportResults(res.message_id, results)

      // Kept inside `send`'s try so `sending` (and the panel spinner) stays true
      // across the slow generation; a per-image assistant note reports each one.
      // `block` may be a same-turn add_block's temp id — remap through the
      // map applying the sync ops just built, same as applyMerlinOps does
      // internally for every other op that can target one.
      if (genOps.length) {
        const remapped = genOps.map((g) => ({ ...g, block: applied.tempIdMap[g.block] ?? g.block }))
        await runImageOps(siteId, remapped, sentForPageId, sentSession)
      }
    } catch (e) {
      // An aborted turn is a normal interaction (the user navigated away), not
      // a failure — don't drop an error note into the destination page's panel.
      if (abort.signal.aborted) return
      const msg = e instanceof Error ? e.message : 'Merlin failed to respond'
      setError(msg)
      setMessages((m) => [...m, { role: 'assistant', content: `Something went wrong: ${msg}` }])
    } finally {
      if (abortRef.current === abort) abortRef.current = null
      setStatus(null)
      setLiveSteps([])
      setSending(false)
    }
  }

  return {
    open, setOpen, messages, send, sending, error, tier, setTier, width, setWidth, setWidthLive,
    expanded, setExpanded,
    status, liveSteps, schema, getImageTargets, applyImageTo, generateImage,
    attachments, addAttachment, addAttachmentFromUrl, removeAttachment, attachmentUploading, attachmentError,
    conversationId, conversations, openConversation, newConversation,
    renameConversation, deleteConversation,
  }
}
