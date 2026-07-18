import { useCallback, useEffect, useRef, useState } from 'react'
import {
  BookOpen, HelpCircle, Loader2, MessageSquarePlus, Plus, Sparkles, Wand2,
} from 'lucide-react'
import {
  listPilotSessions, getPilotSession, getPilotContext,
  type PilotSession, type ContextPreview, type CoverageEntry,
} from '../../../api/handbook-pilot/handbookPilot'
import { HowItWorksModal } from '../../../components/ui/HowItWorksModal'
import { HelpHint } from '../../../components/ui/HelpHint'
import { useShowOnce } from '../../../hooks/useShowOnce'
import HandbookViewer from './HandbookViewer'
import { HOW_IT_WORKS_STEPS } from './howItWorksSteps'
import type { ComposerSeed } from './shared'
import { Console } from './Console'
import { DraftsPanel } from './DraftsPanel'
import { RailTabs } from './RailTabs'
import { NewSessionModal } from './NewSessionModal'

// ---------------------------------------------------------------------------
// Handbook Pilot — conversational, grounded handbook/policy generation.
// Chat with an AI grounded in your profile + applicable law + existing
// policies; it proposes citation-validated drafts you review, edit, and
// promote into the real handbooks / policies tables.
// ---------------------------------------------------------------------------

export default function HandbookPilot() {
  const [sessions, setSessions] = useState<PilotSession[]>([])
  const [active, setActive] = useState<PilotSession | null>(null)
  const [context, setContext] = useState<ContextPreview | null>(null)
  const [loading, setLoading] = useState(true)
  const [showNew, setShowNew] = useState(false)
  const [showHelp, setShowHelp] = useShowOnce('handbook-pilot')
  const [mode, setMode] = useState<'build' | 'handbook'>('build')
  const [seed, setSeed] = useState<ComposerSeed | null>(null)
  // The session the user just created in this view — its goal auto-sends as
  // the first chat turn. Never cleared; inert once the session has messages.
  const [justCreatedId, setJustCreatedId] = useState<string | null>(null)
  // Bumped whenever drafts may have changed (chat turn, edit, promote) or when
  // the viewer is (re)entered, so the read-only viewer refetches its snapshot.
  const [viewerVersion, setViewerVersion] = useState(0)
  const activeIdRef = useRef<string | null>(null)

  const refreshList = useCallback(async () => {
    const rows = await listPilotSessions()
    setSessions(rows)
    return rows
  }, [])

  const openSession = useCallback(async (id: string) => {
    activeIdRef.current = id
    setContext(null)
    setSeed(null)  // a requirement picked in one session never leaks into the next
    try {
      const [full, ctx] = await Promise.all([
        getPilotSession(id),
        getPilotContext(id).catch(() => null),
      ])
      if (activeIdRef.current !== id) return
      setActive(full)
      setContext(ctx)
    } catch {
      if (activeIdRef.current === id) setActive(null)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const rows = await refreshList()
        if (cancelled) return
        if (rows.length) void openSession(rows[0].id)
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const reloadActive = useCallback(async () => {
    const id = activeIdRef.current
    if (!id) return
    try {
      const full = await getPilotSession(id)
      if (activeIdRef.current === id) setActive(full)
    } catch { /* keep current view */ }
    setViewerVersion((v) => v + 1)
    void refreshList()
  }, [refreshList])

  const showHandbook = useCallback(() => {
    setViewerVersion((v) => v + 1)  // refetch on entry so post-edit changes show
    setMode('handbook')
  }, [])

  // A requirement nothing cites yet → a targeted prompt in the composer. We
  // prefill rather than send: the admin gets to add context (and a mis-click
  // never burns a drafting turn).
  const draftRequirement = useCallback((req: CoverageEntry) => {
    const where = req.jurisdiction && req.jurisdiction !== req.state
      ? `${req.state} — ${req.jurisdiction}`
      : req.state
    setSeed({
      text: `Draft a handbook section covering this requirement: ${req.title} (${where}). `
        + `Ground every enforceable clause in [${req.cid}] and any related requirements in the corpus.`,
      nonce: Date.now(),
    })
    setMode('build')
  }, [])

  const onCreated = useCallback(async (s: PilotSession) => {
    setShowNew(false)
    setJustCreatedId(s.id)
    await refreshList()
    void openSession(s.id)
  }, [refreshList, openSession])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-72">
        <Loader2 className="h-6 w-6 animate-spin text-emerald-500" />
      </div>
    )
  }

  return (
    <div className="flex h-[calc(100vh-7rem)] gap-4">
      {/* Sessions rail — hidden in Handbook mode so the document gets the full
          reading width; the Build/Handbook toolbar stays as the way back. */}
      <aside className={`w-64 shrink-0 flex-col border border-zinc-800 rounded-xl bg-zinc-950/40 ${
        active && mode === 'handbook' ? 'hidden' : 'flex'}`}>
        <div className="p-3 border-b border-zinc-800 flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Sparkles className="h-4 w-4 text-emerald-500" />
            <span className="text-sm font-semibold text-zinc-200">Handbook Pilot</span>
            <HelpHint text="Drafts cite real jurisdiction requirements for your work locations — nothing is generated from generic templates." />
          </div>
          <div className="flex items-center gap-0.5">
            <button
              onClick={() => setShowHelp(true)}
              className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-400 hover:text-emerald-400"
              title="How it works"
            >
              <HelpCircle className="h-4 w-4" />
            </button>
            <button
              onClick={() => setShowNew(true)}
              className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-400 hover:text-emerald-400"
              title="New session"
            >
              <Plus className="h-4 w-4" />
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {sessions.length === 0 && (
            <p className="text-xs text-zinc-600 p-3">No sessions yet. Start one to draft a handbook section or policy.</p>
          )}
          {sessions.map((s) => (
            <button
              key={s.id}
              onClick={() => openSession(s.id)}
              className={`w-full text-left px-3 py-2 rounded-lg transition ${
                active?.id === s.id ? 'bg-emerald-500/10 border border-emerald-500/30' : 'hover:bg-zinc-800/60 border border-transparent'
              }`}
            >
              <div className="text-sm text-zinc-200 truncate">{s.title}</div>
              <div className="text-[11px] text-zinc-500 flex gap-2 mt-0.5">
                <span>{s.draft_count ?? 0} drafts</span>
                {(s.promoted_count ?? 0) > 0 && <span className="text-emerald-500">{s.promoted_count} promoted</span>}
              </div>
            </button>
          ))}
        </div>
      </aside>

      {/* Workbench */}
      <main className="flex-1 min-w-0 flex flex-col gap-3">
        {active ? (
          <>
            <div className="flex items-center justify-end shrink-0">
              <div className="inline-flex items-center gap-1 rounded-lg border border-zinc-800 bg-zinc-950/40 p-0.5">
                <button
                  onClick={() => setMode('build')}
                  className={`px-3 py-1 text-xs rounded-md inline-flex items-center gap-1.5 ${
                    mode === 'build' ? 'bg-zinc-800 text-emerald-400' : 'text-zinc-500 hover:text-zinc-300'}`}
                >
                  <MessageSquarePlus className="h-3.5 w-3.5" /> Build
                </button>
                <button
                  onClick={showHandbook}
                  className={`px-3 py-1 text-xs rounded-md inline-flex items-center gap-1.5 ${
                    mode === 'handbook' ? 'bg-zinc-800 text-emerald-400' : 'text-zinc-500 hover:text-zinc-300'}`}
                >
                  <BookOpen className="h-3.5 w-3.5" /> Handbook
                </button>
              </div>
            </div>
            {mode === 'build' ? (
              <div className="flex-1 min-h-0 flex gap-4">
                <div className="flex-1 min-w-0 flex flex-col border border-zinc-800 rounded-xl bg-zinc-950/40">
                  {/* key by session id → remount (and reset transcript/abort the
                      stream) when the user switches sessions mid-turn */}
                  <Console
                    key={active.id}
                    session={active}
                    onTurn={reloadActive}
                    seed={seed}
                    onSeedConsumed={() => setSeed(null)}
                    autoSeed={active.id === justCreatedId}
                  />
                </div>
                <div className="w-80 shrink-0 flex flex-col gap-4 overflow-y-auto">
                  <DraftsPanel key={active.id} session={active} onChange={reloadActive} />
                  <RailTabs
                    key={active.id}
                    sessionId={active.id}
                    refreshKey={viewerVersion}
                    context={context}
                    onDraft={draftRequirement}
                  />
                </div>
              </div>
            ) : (
              <div className="flex-1 min-h-0 flex">
                <HandbookViewer
                  key={active.id}
                  sessionId={active.id}
                  refreshKey={viewerVersion}
                  onDraftRequirement={draftRequirement}
                />
              </div>
            )}
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-center">
            <Wand2 className="h-8 w-8 text-emerald-500 mb-3" />
            <h2 className="text-lg font-semibold text-zinc-100">Draft a handbook or policy</h2>
            <p className="text-sm text-zinc-500 mt-2 max-w-md">
              Describe what you need — a meal-and-rest-break policy, an updated anti-harassment
              section — and the pilot drafts it grounded in your profile, the law where you operate,
              and your existing policies. Review, then promote it into your handbooks or policies.
            </p>
            <button
              onClick={() => setShowNew(true)}
              className="mt-5 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium inline-flex items-center gap-2"
            >
              <Plus className="h-4 w-4" /> New session
            </button>
          </div>
        )}
      </main>

      {showNew && <NewSessionModal onClose={() => setShowNew(false)} onCreated={onCreated} />}
      {showHelp && (
        <HowItWorksModal
          title="How Handbook Pilot works"
          steps={HOW_IT_WORKS_STEPS}
          onClose={() => setShowHelp(false)}
        />
      )}
    </div>
  )
}
