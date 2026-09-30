import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Plus, Pin, Archive, Loader2, FileText, Presentation, Users, X, Hash, Compass, ShieldAlert, KanbanSquare, Search, ArrowUp, Sparkles } from 'lucide-react'
import { THREAD_MODE_TOGGLES } from '../components/panels/constants'
import { formatDateTimePacific } from '../../utils/dateFormat'
import { useMe } from '../../hooks/useMe'
import OnboardingWizard from '../components/shell/OnboardingWizard'
import { useMatchaWorkList } from './useMatchaWorkList'
import { PickUp, UpNext } from './HomeInsights'
import { pickUpItems, useHomeInsights } from './homeData'
import { AssistantConversation, type AssistantAsk } from './Assistant'
import { chatLabel } from '../utils/chatLabel'

const TASK_LABELS: Record<string, string> = {
  chat: 'Chat',
  offer_letter: 'Offer Letter',
  review: 'Review',
  workbook: 'Workbook',
  onboarding: 'Onboarding',
  presentation: 'Presentation',
  handbook: 'Handbook',
  policy: 'Policy',
}

// Home is a desk, not a dashboard: say hello, take the next request, show
// what's waiting and what was left open. One display face (the greeting),
// everything else in the app's own type.
const DISPLAY = "font-['Instrument_Serif',Georgia,serif] font-normal"
const MONO = "font-['JetBrains_Mono',ui-monospace,monospace]"

// Things Espresso really does (web, shopping, flights, email, calendar,
// bookings). Shown one at a time in the empty composer.
const ASK_EXAMPLES = [
  'Find a quiet standing desk under $400',
  'Reply to the landlord and say Friday works',
  'Compare nonstop flights to Denver next weekend',
  'Book Nopa for four on Friday at 7',
  'What’s on my calendar tomorrow?',
  'Buy the best pick',
]

function greeting(now: Date): string {
  const h = now.getHours()
  return h < 5 ? 'Up late' : h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'
}

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

/** A labelled section with a hairline under its heading; no box around it. */
function Section({ title, meta, action, children }: {
  title: string
  meta?: React.ReactNode
  action?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <section>
      <div className="mb-2 flex items-baseline gap-2 border-b border-w-line px-2 pb-2">
        <h2 className="text-[13px] font-semibold text-w-text">{title}</h2>
        {meta && <span className={`${MONO} text-[10px] text-w-faint`}>{meta}</span>}
        <span className="flex-1" />
        {action}
      </div>
      {children}
    </section>
  )
}

/** The one loud thing on the page: ask Espresso, from right here. */
function AskComposer({ onAsk }: { onAsk: (text: string) => void }) {
  const [text, setText] = useState('')
  const [example, setExample] = useState(0)
  const [focused, setFocused] = useState(false)

  useEffect(() => {
    if (text || focused || prefersReducedMotion()) return
    const timer = window.setInterval(() => setExample((i) => (i + 1) % ASK_EXAMPLES.length), 4000)
    return () => window.clearInterval(timer)
  }, [text, focused])

  function submit(event: FormEvent) {
    event.preventDefault()
    const ask = text.trim()
    if (!ask) return
    onAsk(ask)
    setText('')
  }

  return (
    <form
      onSubmit={submit}
      className="group relative flex items-center gap-3 rounded-2xl border border-w-line bg-w-surface px-4 py-3 shadow-[0_1px_0_0_rgba(255,255,255,0.03)_inset] transition-colors focus-within:border-w-accent/60"
    >
      {/* The crema line: a thin warm edge that pours across the top when you start typing. */}
      <span
        aria-hidden
        className={`pointer-events-none absolute inset-x-6 -top-px h-px origin-left bg-gradient-to-r from-transparent via-w-accent to-transparent transition-transform duration-700 motion-reduce:transition-none ${text || focused ? 'scale-x-100' : 'scale-x-0'}`}
      />
      <Sparkles size={17} className="shrink-0 text-w-accent" />
      <label htmlFor="home-ask" className="sr-only">Ask Espresso</label>
      <input
        id="home-ask"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        placeholder={`Ask Espresso… ${ASK_EXAMPLES[example]}`}
        autoComplete="off"
        className="min-w-0 flex-1 bg-transparent text-[15px] text-w-text placeholder:text-w-faint focus:outline-none"
      />
      <button
        type="submit"
        disabled={!text.trim()}
        aria-label="Ask"
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-w-accent text-w-on-accent transition-opacity disabled:opacity-30"
      >
        <ArrowUp size={15} />
      </button>
    </form>
  )
}

export default function MatchaWorkList() {
  const {
    base,
    navigate,
    channels,
    loading,
    creating,
    showTypePicker,
    setShowTypePicker,
    tab,
    setTab,
    query,
    setQuery,
    error,
    showOnboarding,
    setShowOnboarding,
    tabs,
    firstName,
    searching,
    threads,
    matchedProjects,
    matchedThreads,
    handleCreate,
    handleCreateProject,
    handlePin,
    handleArchive,
  } = useMatchaWorkList()
  const { isPersonal } = useMe()
  const insights = useHomeInsights()
  const [ask, setAsk] = useState<AssistantAsk | null>(null)
  const [panelOpen, setPanelOpen] = useState(false)
  const [panelIn, setPanelIn] = useState(false)
  const askCount = useRef(0)
  const now = new Date()

  // Slide the panel in on the frame after it mounts, so the transform animates.
  useEffect(() => {
    if (!panelOpen) return
    const frame = window.requestAnimationFrame(() => setPanelIn(true))
    return () => window.cancelAnimationFrame(frame)
  }, [panelOpen])

  function closePanel() {
    setPanelOpen(false)
    setPanelIn(false)
  }

  function handleAsk(text: string) {
    askCount.current += 1
    setAsk({ id: askCount.current, text })
    setPanelOpen(true)
  }

  const recent = pickUpItems(insights.activity, threads, base)
  const unreadChannels = channels.filter((c) => c.is_member && c.unread_count > 0)
  const quietChannels = channels.filter((c) => c.is_member && c.unread_count === 0).slice(0, Math.max(0, 4 - unreadChannels.length))

  return (
    <div className="flex h-full min-h-0">
      <div className="min-w-0 flex-1 overflow-y-auto">
        <div className={`mx-auto px-4 py-8 sm:px-8 sm:py-12 ${panelOpen ? 'max-w-3xl' : 'max-w-5xl'}`}>
          <header className="mb-10">
            <p className={`${MONO} mb-3 text-[11px] uppercase tracking-[0.14em] text-w-faint`}>
              {now.toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' })}
            </p>
            <h1 className={`${DISPLAY} text-[40px] leading-[1.05] tracking-tight text-w-text sm:text-[52px]`}>
              {greeting(now)}{firstName ? <>, <em className="text-w-accent">{firstName}</em></> : ''}.
            </h1>
            <div className="mt-7">
              {isPersonal ? (
                <AskComposer onAsk={handleAsk} />
              ) : (
                <div className="relative">
                  <Search size={15} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-w-faint" />
                  <input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Search chats and workspaces…"
                    className="h-12 w-full rounded-2xl border border-w-line bg-w-surface pl-11 pr-3 text-[15px] text-w-text placeholder:text-w-faint transition-colors focus:border-w-accent/60 focus:outline-none"
                  />
                </div>
              )}
              <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 px-1 text-[13px]">
                <button onClick={handleCreate} disabled={creating} className="inline-flex items-center gap-1.5 text-w-dim transition-colors hover:text-w-text disabled:opacity-50">
                  {creating ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />} New chat
                </button>
                <button onClick={() => setShowTypePicker(true)} disabled={creating} className="inline-flex items-center gap-1.5 text-w-dim transition-colors hover:text-w-text disabled:opacity-50">
                  <KanbanSquare size={14} /> New workspace
                </button>
                <button onClick={() => navigate(`${base}/channels`)} className="inline-flex items-center gap-1.5 text-w-dim transition-colors hover:text-w-text">
                  <Compass size={14} /> Browse channels
                </button>
              </div>
            </div>
          </header>

          {insights.error && <p role="alert" className="mb-6 text-xs text-red-400">{insights.error}</p>}

          <div className={`grid gap-x-12 gap-y-10 ${panelOpen ? '' : 'lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]'}`}>
            <Section title="Up next" meta={insights.loaded ? `${insights.tasks.length} open` : undefined}>
              {insights.loaded ? <UpNext tasks={insights.tasks} base={base} /> : <Loader2 size={16} className="m-2 animate-spin text-w-faint" />}
            </Section>

            <div className="space-y-10">
              <Section title="Pick up where you left off">
                <PickUp items={recent} />
              </Section>

              {(unreadChannels.length > 0 || quietChannels.length > 0) && (
                <Section
                  title="Channels"
                  meta={unreadChannels.length > 0 ? `${unreadChannels.length} unread` : undefined}
                  action={<button onClick={() => navigate(`${base}/channels`)} className="text-[11px] text-w-dim hover:text-w-accent">Browse all</button>}
                >
                  <ul>
                    {[...unreadChannels, ...quietChannels].map((ch) => (
                      <li key={ch.id}>
                        <button onClick={() => navigate(`${base}/channels/${ch.id}`)} className="flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left hover:bg-w-surface2/70">
                          <Hash size={13} className={ch.unread_count > 0 ? 'text-w-accent' : 'text-w-dim'} />
                          <span className={`min-w-0 flex-1 truncate text-sm ${ch.unread_count > 0 ? 'font-semibold text-w-text' : 'text-w-dim'}`}>{ch.name}</span>
                          {ch.unread_count > 0 && (
                            <span className={`${MONO} rounded-full bg-w-accent px-1.5 text-[10px] font-bold text-w-on-accent`}>
                              {ch.unread_count > 9 ? '9+' : ch.unread_count}
                            </span>
                          )}
                        </button>
                      </li>
                    ))}
                  </ul>
                </Section>
              )}
            </div>
          </div>

          {matchedProjects.length > 0 && (
            <div className="mt-12">
              <Section title="Workspaces" meta={matchedProjects.length}>
                <div className="flex gap-2.5 overflow-x-auto pb-1 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                  {matchedProjects.slice(0, 10).map((p) => {
                    const Icon = p.project_type === 'presentation' ? Presentation : p.project_type === 'recruiting' ? Users : FileText
                    return (
                      <button
                        key={p.id}
                        onClick={() => navigate(`${base}/projects/${p.id}`)}
                        className="flex w-48 shrink-0 items-center gap-2 rounded-xl border border-w-line bg-w-surface px-3 py-2.5 text-left transition-colors hover:border-w-accent/50"
                      >
                        <Icon size={14} className="shrink-0 text-w-accent" />
                        <span className="truncate text-[13px] font-medium text-w-text">{p.title}</span>
                        {p.is_pinned && <Pin size={11} className="ml-auto shrink-0 text-w-faint" />}
                      </button>
                    )
                  })}
                </div>
              </Section>
            </div>
          )}

          {/* Every chat: pin, archive, and the Archived filter archiving points back to. */}
          <div className="mt-12">
            <Section
              title="All chats"
              action={
                <div className="flex items-center gap-1 overflow-x-auto whitespace-nowrap [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                  {isPersonal && (
                    <label className="relative mr-1">
                      <span className="sr-only">Search chats</span>
                      <Search size={12} className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-w-faint" />
                      <input
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        placeholder="Search"
                        className="h-7 w-32 rounded-full border border-w-line bg-transparent pl-6 pr-2 text-[11px] text-w-text placeholder:text-w-faint focus:border-w-accent/60 focus:outline-none"
                      />
                    </label>
                  )}
                  {tabs.map((t) => (
                    <button
                      key={t.key}
                      onClick={() => setTab(t.key)}
                      className={`rounded-full px-2.5 py-1 text-[11px] font-medium transition-colors ${
                        tab === t.key ? 'bg-w-accent/15 text-w-accent' : 'text-w-dim hover:bg-w-surface2 hover:text-w-text'
                      }`}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>
              }
            >
              {error && <div className="mb-3 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">{error}</div>}
              {loading ? (
                <div className="flex justify-center py-10"><Loader2 className="animate-spin text-w-faint" size={20} /></div>
              ) : matchedThreads.length === 0 ? (
                <p className="px-2 py-8 text-center text-sm text-w-faint">
                  {searching ? 'No chats match that.' : tab === 'pinned' ? 'Nothing pinned. Pin a chat to keep it at the top.' : 'No chats yet. Start one with New chat.'}
                </p>
              ) : (
                <ul>
                  {matchedThreads.map((t) => (
                    <li
                      key={t.id}
                      onClick={() => navigate(`${base}/${t.id}`)}
                      className="group flex cursor-pointer items-center gap-3 rounded-lg px-2 py-2 transition-colors hover:bg-w-surface2/70"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          {t.is_pinned && <Pin size={11} className="shrink-0 text-w-accent" />}
                          <span className="truncate text-[13px] font-medium text-w-text" title={t.title}>{chatLabel(t.title)}</span>
                          {t.task_type && (
                            <span className="shrink-0 rounded-full bg-w-surface2 px-1.5 py-0.5 text-[10px] font-medium text-w-dim">
                              {TASK_LABELS[t.task_type] ?? t.task_type}
                            </span>
                          )}
                          {THREAD_MODE_TOGGLES.filter((m) => t[`${m.key}_mode`]).map((m) => (
                            <span key={m.key} className={`shrink-0 rounded-full px-1.5 py-0.5 text-[11px] font-medium sm:text-[10px] ${m.badgeClass}`}>
                              {m.label}
                            </span>
                          ))}
                        </div>
                      </div>
                      <span className={`${MONO} shrink-0 text-[10px] text-w-faint sm:group-hover:hidden`} title="Created (Pacific time)">
                        {formatDateTimePacific(t.created_at)}
                      </span>
                      {t.status !== 'archived' && (
                        <div className="flex items-center gap-1 sm:hidden sm:group-hover:flex">
                          <button onClick={(e) => handlePin(e, t)} className={`rounded-md p-1.5 hover:bg-w-surface ${t.is_pinned ? 'text-w-accent' : 'text-w-faint'}`} title={t.is_pinned ? 'Unpin' : 'Pin'}>
                            <Pin size={14} />
                          </button>
                          <button onClick={(e) => handleArchive(e, t)} className="rounded-md p-1.5 text-w-faint hover:bg-w-surface" title="Archive">
                            <Archive size={14} />
                          </button>
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </Section>
          </div>
        </div>
      </div>

      {/* Espresso answers here, beside Home, instead of taking you away from it. */}
      {panelOpen && (
        <aside
          aria-label="Espresso"
          className={`fixed inset-0 z-40 flex flex-col border-l border-w-line bg-w-bg transition-transform duration-300 ease-out motion-reduce:transition-none lg:static lg:inset-auto lg:z-auto lg:w-[440px] lg:shrink-0 xl:w-[500px] ${panelIn ? 'translate-x-0' : 'translate-x-full'}`}
        >
          <AssistantConversation ask={ask} onClose={closePanel} />
        </aside>
      )}

      {showOnboarding && <OnboardingWizard onDismiss={() => setShowOnboarding(false)} />}

      {showTypePicker && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="mx-4 w-full max-w-sm rounded-2xl border border-w-line bg-w-surface p-6">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="font-semibold text-w-text">New workspace</h2>
              <button onClick={() => setShowTypePicker(false)} className="text-w-faint hover:text-w-text" aria-label="Close">
                <X size={16} />
              </button>
            </div>
            <p className="mb-4 text-sm text-w-dim">What kind of workspace?</p>
            <div className="space-y-2">
              {[
                { type: 'general' as const, icon: FileText, label: 'Research / Report', desc: 'Build documents and plans from chat' },
                { type: 'presentation' as const, icon: Presentation, label: 'Presentation', desc: 'Create slide decks and pitch materials' },
                { type: 'recruiting' as const, icon: Users, label: 'Job Posting', desc: 'Recruiting pipeline with resumes and interviews' },
                { type: 'discipline' as const, icon: ShieldAlert, label: 'Performance Action', desc: 'Draft, sign, and close a written warning' },
              ].map((opt) => (
                <button
                  key={opt.type}
                  onClick={() => handleCreateProject(opt.type)}
                  className="flex w-full items-center gap-3 rounded-xl border border-w-line p-3 text-left transition-colors hover:border-w-accent/60 hover:bg-w-surface2"
                >
                  <opt.icon size={20} className="shrink-0 text-w-accent" />
                  <div>
                    <p className="text-sm font-medium text-w-text">{opt.label}</p>
                    <p className="text-xs text-w-dim">{opt.desc}</p>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
