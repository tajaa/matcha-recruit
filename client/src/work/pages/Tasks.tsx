import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { AlertTriangle, BookOpen, Briefcase, ClipboardList, Film, Loader2, Settings } from 'lucide-react'
import { useMe } from '../../hooks/useMe'
import { useWorkBase } from '../routes/WorkSurfaceContext'
import { useEntitlements } from '../hooks/useEntitlements'
import { notifyTasksChanged } from '../hooks/useTasksSummary'
import type { AgentTask, AgentTaskAction, AgentTaskItemDetail, AgentTaskList } from '../types'
import type { JobSearchSummary } from '../api/matchaWork/jobSearch'
import { getAgentTaskForSearch } from '../api/matchaWork/agentTasks'
import {
  askEspressoPrompt, canFollowUp, displayTitle, groupTasks, isJobSearch, isLive, isWaiting, rowMeta, statusLabel,
  usageLine,
} from '../components/tasks/tasksLogic'
import { useTasks } from './Tasks/useTasks'
import TaskDetail from './Tasks/TaskDetail'
import ItemPane from './Tasks/ItemPane'
import ActionModal from './Tasks/ActionModal'
import TasksGuide, { TASKS_GUIDE_SEEN_KEY } from './Tasks/TasksGuide'
import JobSearchPane from './Tasks/JobSearchPane'
import NewJobSearch from './Tasks/NewJobSearch'
import RecapList from '../components/recaps/RecapList'
import RecapView from '../components/recaps/RecapView'
import { recapsPath } from '../components/recaps/paths'
import { useRecapPreferences } from '../hooks/useRecapPreferences'
import type { AssistantDraftState } from './Assistant'

function guideSeen(): boolean {
  try { return localStorage.getItem(TASKS_GUIDE_SEEN_KEY) === '1' } catch { return true }
}

/** Wide enough for the list and a task side by side (Tailwind's `md`). */
const wide = () => typeof window !== 'undefined' && window.matchMedia('(min-width: 768px)').matches

/**
 * Espresso Tasks on the web: the person's background tasks on the left (needs
 * you, running, done), the open task's findings in the middle, and the open
 * finding on the right, each fact with the words and page it came from. The
 * same tasks, API and rules as the macOS app's Tasks section. A job search is
 * a task too; its own view opens here, with its ranked jobs. Personal accounts only.
 */
export default function Tasks() {
  const { isPersonal } = useMe()
  if (!isPersonal) {
    return <p className="p-6 text-sm text-w-dim">Tasks come with a personal Espresso account.</p>
  }
  return <TasksPage />
}

function TasksPage() {
  const base = useWorkBase()
  const navigate = useNavigate()
  const { taskId } = useParams<{ taskId?: string }>()
  const [params, setParams] = useSearchParams()
  const itemId = params.get('item')
  // Recaps are a second view of the same page (`?view=recaps`): the list on
  // the left, the open recap in the middle. It shows for anyone recaps are
  // available to, and for anyone a link sent here (they may still own some).
  const recapsView = !taskId && params.get('view') === 'recaps'
  const recapId = recapsView ? params.get('recap') : null
  const recapSource = recapsView ? params.get('source_id') : null
  const recapsOffered = !!useRecapPreferences()?.available || recapsView
  const { me } = useMe()
  const t = useTasks(taskId, itemId)
  const { tasksEnabled, jobSearchEnabled } = useEntitlements()
  const [helpOpen, setHelpOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [guideDone, setGuideDone] = useState(guideSeen)
  const [journalId, setJournalId] = useState<string | null>(null)
  const [acting, setActing] = useState<{ item: AgentTaskItemDetail; action: AgentTaskAction } | null>(null)
  const { chainDetail: detail, list, open, jobSearchId } = t
  const closeNewSearch = useCallback(() => setCreating(false), [])
  const guideOpen = helpOpen || (list !== null && !guideDone)

  // The sidebar's count follows what this page has just seen, when that changes.
  const seenKey = list ? list.tasks.map((task) => `${task.id}:${task.status}:${task.unseen ? 1 : 0}`).join() : null
  useEffect(() => { if (seenKey !== null) notifyTasksChanged() }, [seenKey])

  // Nothing open on a wide screen: open the first task, as the Mac does.
  useEffect(() => {
    if (taskId || recapsView || !list || !wide()) return
    const first = groupTasks(list.tasks)[0]?.[1][0]
    if (first) navigate(`${base}/tasks/${encodeURIComponent(first.id)}`, { replace: true })
  }, [taskId, recapsView, list, base, navigate])

  const setItemParam = useCallback((id: string | null) => {
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      if (id) next.set('item', id)
      else next.delete('item')
      return next
    }, { replace: !!itemId })
  }, [setParams, itemId])

  // A finding that is no longer in the task (a stale link) closes.
  useEffect(() => {
    if (detail && itemId && !(detail.items ?? []).some((i) => i.id === itemId)) setItemParam(null)
  }, [detail, itemId, setItemParam])

  function closeGuide() {
    try { localStorage.setItem(TASKS_GUIDE_SEEN_KEY, '1') } catch { /* best effort */ }
    setHelpOpen(false)
    setGuideDone(true)
  }

  function openTask(task: AgentTask) {
    setJournalId(null)
    navigate(`${base}/tasks/${encodeURIComponent(task.id)}`)
  }

  /** The words go to Espresso's chat, ready to send: it asks for anything
   *  missing with a form there, and submitting that starts the task. */
  function askEspresso(text: string) {
    const state: AssistantDraftState = { draft: { id: Date.now(), text } }
    navigate(`${base}/assistant`, { state })
  }

  async function removeTask() {
    if (!open) return
    const message = isJobSearch(open)
      ? "Delete this task? Its jobs and drafts are removed. It still counts toward this month's units."
      : "Delete this task? What it found is removed. It still counts toward this month's units."
    if (!window.confirm(message)) return
    if (await t.remove(open.id)) navigate(`${base}/tasks`, { replace: true })
  }

  /** Open the new search's task, found by the exact lookup (a list refresh
   *  can't lose it). If that misses, the search's own link looks again and
   *  offers a retry there. */
  async function searchCreated(search: JobSearchSummary) {
    setCreating(false)
    try {
      const task = await getAgentTaskForSearch(search.id)
      navigate(`${base}/tasks/${encodeURIComponent(task.id)}`)
    } catch {
      navigate(`${base}/jobs/${encodeURIComponent(search.id)}`)
    }
  }

  async function makeDocument() {
    setJournalId(await t.startRound('document'))
  }

  const tabs = recapsOffered ? (
    <ViewTabs
      view={recapsView ? 'recaps' : 'tasks'}
      onTasks={() => navigate(`${base}/tasks`)}
      onRecaps={() => navigate(recapsPath(base))}
    />
  ) : null

  if (recapsView) {
    return (
      <div className="flex h-full min-h-0">
        <aside className={`min-h-0 w-full shrink-0 flex-col border-r border-w-line bg-w-surface md:w-72 ${recapId ? 'hidden md:flex' : 'flex'}`}>
          <div className="space-y-2 border-b border-w-line px-4 py-3">
            <div className="flex items-center gap-2">
              {tabs}
              <button type="button" onClick={() => navigate(`${base}/settings`)} aria-label="Recap settings" title="Recap settings"
                className="rounded-md p-1 text-w-dim hover:bg-w-surface2 hover:text-w-text">
                <Settings size={13} />
              </button>
            </div>
            <p className="text-[10px] leading-4 text-w-dim">Short private videos of a task's key steps and results.</p>
            {recapSource && (
              <button type="button" onClick={() => navigate(recapsPath(base, { recap: recapId }))}
                className="text-[10px] text-w-accent hover:underline">Showing one task's recaps · Show all</button>
            )}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
            <RecapList owner={me?.user.id} source={recapSource} selectedId={recapId}
              onOpen={(recap) => navigate(recapsPath(base, { recap: recap.id, source: recapSource }))} />
          </div>
        </aside>
        <main className={`min-h-0 min-w-0 flex-1 flex-col overflow-y-auto ${recapId ? 'flex' : 'hidden md:flex'}`}>
          {recapId ? (
            <RecapView
              key={recapId}
              recapId={recapId}
              onDeleted={() => navigate(recapsPath(base, { source: recapSource }), { replace: true })}
              onBack={() => navigate(recapsPath(base, { source: recapSource }))}
            />
          ) : (
            <Message icon={<Film size={28} className="text-w-faint" />} title="Open a recap on the left"
              text="Each recap is a short video of what a task did: the request, the pages it looked at, what needs your attention, and the result." />
          )}
        </main>
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0">
      <TaskList
        tabs={tabs}
        list={list}
        error={t.listError}
        loadingOlder={t.loadingOlder}
        olderError={t.olderError}
        onOlder={() => void t.loadOlder()}
        selectedId={taskId ?? null}
        hiddenOnSmall={!!taskId}
        tasksEnabled={tasksEnabled}
        canSearchJobs={jobSearchEnabled}
        onOpen={openTask}
        onAsk={askEspresso}
        onNewJobSearch={() => setCreating(true)}
        onHelp={() => setHelpOpen(true)}
        onRetry={() => void t.loadList()}
      />

      <main className={`min-h-0 min-w-0 flex-1 flex-col ${taskId ? 'flex' : 'hidden md:flex'}`}>
        {!taskId ? (
          <EmptyState list={list} error={t.listError} tasksEnabled={tasksEnabled} onNewJobSearch={jobSearchEnabled ? () => setCreating(true) : undefined} />
        ) : jobSearchId ? (
          <JobSearchPane
            key={jobSearchId}
            searchId={jobSearchId}
            leadId={itemId}
            onSelectLead={setItemParam}
            onBack={() => navigate(`${base}/tasks`)}
            onDelete={() => void removeTask()}
            onChanged={t.syncSearchStatus}
            guideBlocked={guideOpen || !list || creating}
            deleting={t.busy}
            deleteError={t.error}
            onDismissDeleteError={() => t.setError(null)}
          />
        ) : detail ? (
          <TaskDetail
            key={detail.id}
            detail={detail}
            busy={t.busy}
            error={t.error}
            onDismissError={() => t.setError(null)}
            journalPath={journalId ? `${base}/journals/${encodeURIComponent(journalId)}` : null}
            onDismissJournal={() => setJournalId(null)}
            selectedItemId={itemId}
            onSelectItem={(id) => setItemParam(id)}
            onCancel={() => void t.cancel()}
            onRefine={(change) => void t.startRound('refine', change)}
            onMore={() => void t.startRound('more')}
            onDocument={() => void makeDocument()}
            onAskEspresso={() => askEspresso(askEspressoPrompt(detail.id))}
            onDelete={() => void removeTask()}
            onBack={() => navigate(`${base}/tasks`)}
          />
        ) : t.detailError ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
            <AlertTriangle size={28} className="text-w-faint" />
            <p className="text-sm font-semibold text-w-text">Couldn't load this task</p>
            <p className="max-w-md text-xs text-w-dim">{t.detailError}</p>
            <button type="button" onClick={() => void t.loadDetail(taskId)} className="rounded-md bg-w-accent px-3 py-1.5 text-xs font-semibold text-white hover:bg-w-accent-hi">
              Try again
            </button>
          </div>
        ) : (
          <div className="flex flex-1 items-center justify-center"><Loader2 className="animate-spin text-w-dim" /></div>
        )}
      </main>

      {itemId && detail && (
        <ItemPane
          item={t.item}
          loadError={t.itemLoadError}
          error={t.itemError}
          columns={detail.plan?.columns ?? []}
          canFollowUp={canFollowUp(detail)}
          busy={t.busy}
          onClose={() => setItemParam(null)}
          onRetry={() => void t.reloadItem()}
          onDismissError={() => t.setItemError(null)}
          onSetState={(state, id) => void t.setItemState(state, id)}
          onSaveNotes={(notes, id) => void t.saveNotes(notes, id)}
          onMoreLikeThis={(id) => void t.startRound('more', '', [id], id)}
          onAskEspresso={(id) => askEspresso(askEspressoPrompt(detail.id, id))}
          onAction={(item, action) => setActing({ item, action })}
        />
      )}

      {acting && detail && (
        <ActionModal
          taskId={detail.id}
          itemId={acting.item.id}
          itemTitle={acting.item.title}
          action={acting.action}
          onClose={(changed) => {
            setActing(null)
            if (changed) void t.reloadItem()
          }}
        />
      )}
      {creating && <NewJobSearch onCreated={(search) => void searchCreated(search)} onClose={closeNewSearch} />}
      {guideOpen && <TasksGuide onClose={closeGuide} />}
    </div>
  )
}

/** Tasks | Recaps, at the top of the list. */
function ViewTabs({ view, onTasks, onRecaps }: { view: 'tasks' | 'recaps'; onTasks: () => void; onRecaps: () => void }) {
  const tab = (active: boolean) => `inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-semibold transition-colors ${
    active ? 'bg-w-surface2 text-w-text' : 'text-w-dim hover:text-w-text'}`
  return (
    <div role="tablist" aria-label="Tasks or recaps" className="flex flex-1 items-center gap-0.5">
      <button type="button" role="tab" aria-selected={view === 'tasks'} onClick={onTasks} className={tab(view === 'tasks')}>
        <ClipboardList size={13} className={view === 'tasks' ? 'text-w-accent' : ''} /> Tasks
      </button>
      <button type="button" role="tab" aria-selected={view === 'recaps'} onClick={onRecaps} className={tab(view === 'recaps')}>
        <Film size={13} className={view === 'recaps' ? 'text-w-accent' : ''} /> Recaps
      </button>
    </div>
  )
}

function TaskList({
  tabs, list, error, loadingOlder, olderError, onOlder, selectedId, hiddenOnSmall, tasksEnabled, canSearchJobs, onOpen, onAsk, onNewJobSearch, onHelp, onRetry,
}: {
  /** The Tasks | Recaps switch, in place of the heading, when recaps are offered. */
  tabs: React.ReactNode
  list: AgentTaskList | null
  loadingOlder: boolean
  olderError: string | null
  onOlder: () => void
  error: string | null
  selectedId: string | null
  hiddenOnSmall: boolean
  tasksEnabled: boolean
  /** The account can start a job-search task. */
  canSearchJobs: boolean
  onOpen: (task: AgentTask) => void
  onAsk: (directive: string) => void
  onNewJobSearch: () => void
  onHelp: () => void
  onRetry: () => void
}) {
  const [directive, setDirective] = useState('')
  const text = directive.trim()
  const usage = usageLine(list?.usage)

  function ask() {
    if (text.length < 3) return
    setDirective('')
    onAsk(text)
  }

  return (
    <aside className={`min-h-0 w-full shrink-0 flex-col border-r border-w-line bg-w-surface md:w-72 ${hiddenOnSmall ? 'hidden md:flex' : 'flex'}`}>
      <div className="space-y-2 border-b border-w-line px-4 py-3">
        <div className="flex items-center gap-2">
          {tabs ?? <>
            <ClipboardList size={15} className="text-w-accent" />
            <h1 className="flex-1 text-sm font-semibold text-w-text">Tasks</h1>
          </>}
          <button type="button" onClick={onHelp} className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-[11px] text-w-dim hover:bg-w-surface2 hover:text-w-text">
            <BookOpen size={12} /> How it works
          </button>
        </div>
        {tasksEnabled && (
          <div className="space-y-1.5">
            <textarea
              value={directive}
              onChange={(e) => setDirective(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault()
                  ask()
                }
              }}
              rows={2}
              aria-label="What should Espresso go and do?"
              placeholder="What should Espresso go and do?"
              className="w-full resize-none rounded-md border border-w-line bg-w-surface2/40 px-2 py-1.5 text-xs text-w-text placeholder:text-w-faint focus:border-w-accent focus:outline-none"
            />
            <div className="flex items-center gap-2">
              <p className="flex-1 text-[9px] leading-3 text-w-dim">Espresso asks for what it needs, then works in the background.</p>
              <button type="button" onClick={ask} disabled={text.length < 3} className="shrink-0 rounded-md bg-w-accent px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-w-accent-hi disabled:opacity-40">
                Ask Espresso
              </button>
            </div>
          </div>
        )}
        {canSearchJobs && (
          tasksEnabled ? (
            <button type="button" onClick={onNewJobSearch} className="inline-flex items-center gap-1 text-[10px] text-w-accent hover:underline">
              <Briefcase size={11} /> New job search…
            </button>
          ) : (
            <button type="button" onClick={onNewJobSearch} className="flex w-full items-center justify-center gap-1.5 rounded-md border border-w-line px-3 py-1.5 text-xs text-w-text hover:bg-w-surface2">
              <Briefcase size={13} /> New job search
            </button>
          )
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
        {error && !list ? (
          <div className="space-y-2 p-3 text-center">
            <p className="text-xs text-w-dim">{error}</p>
            <button type="button" onClick={onRetry} className="text-xs font-semibold text-w-accent hover:underline">Try again</button>
          </div>
        ) : !list ? (
          <div className="flex justify-center p-6"><Loader2 size={16} className="animate-spin text-w-dim" /></div>
        ) : list.tasks.length === 0 ? (
          <p className="p-3 text-center text-xs leading-5 text-w-dim">Your tasks show up here.</p>
        ) : (
          groupTasks(list.tasks).map(([group, tasks]) => (
            <section key={group}>
              <h2 className={`px-2 pb-0.5 pt-2.5 text-[9px] font-semibold uppercase tracking-wider ${group === 'Needs you' ? 'text-amber-500' : 'text-w-dim'}`}>
                {group}
              </h2>
              <ul className="space-y-0.5">
                {tasks.map((task) => (
                  <li key={task.id}><TaskRow task={task} selected={task.id === selectedId} onOpen={onOpen} /></li>
                ))}
              </ul>
            </section>
          ))
        )}
        {olderError && <p role="alert" className="p-2 text-xs text-amber-500">{olderError}</p>}
        {list?.next_cursor && <button type="button" onClick={onOlder} disabled={loadingOlder}
          className="my-3 w-full rounded-md border border-w-line px-3 py-2 text-xs text-w-text disabled:opacity-50">
          {loadingOlder ? 'Loading…' : 'Load older tasks'}
        </button>}
      </div>
      {usage && <p className="border-t border-w-line px-4 py-2.5 text-[10px] text-w-dim">{usage}</p>}
    </aside>
  )
}

function TaskRow({ task, selected, onOpen }: { task: AgentTask; selected: boolean; onOpen: (task: AgentTask) => void }) {
  const { kind, count } = rowMeta(task)
  const jobs = isJobSearch(task)
  return (
    <button
      type="button"
      onClick={() => onOpen(task)}
      aria-current={selected ? 'page' : undefined}
      className={`flex w-full items-start gap-1.5 rounded-md px-1.5 py-2 text-left ${selected ? 'bg-w-accent/10' : 'hover:bg-w-surface2/60'}`}
    >
      <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${task.unseen ? 'bg-w-accent' : ''}`} aria-label={task.unseen ? 'New' : undefined} />
      <span className="min-w-0 flex-1">
        <span className={`line-clamp-2 text-xs text-w-text ${task.unseen ? 'font-bold' : 'font-semibold'}`}>{displayTitle(task)}</span>
        <span className={`mt-0.5 flex items-center gap-1 truncate text-[10px] ${isWaiting(task) ? 'text-amber-500' : 'text-w-dim'}`}>
          {jobs && <Briefcase size={10} className="shrink-0" aria-label="Job search" />}
          {isLive(task) && <Loader2 size={9} className="shrink-0 animate-spin" />}
          {[kind, statusLabel(task), count].filter(Boolean).join(' · ')}
        </span>
      </span>
    </button>
  )
}

function EmptyState({ list, error, tasksEnabled, onNewJobSearch }: {
  list: AgentTaskList | null; error: string | null; tasksEnabled: boolean; onNewJobSearch?: () => void
}) {
  if (!list) {
    // Never the empty state while it can't load: someone with tasks would think they were gone.
    return error ? (
      <Message icon={<AlertTriangle size={28} className="text-w-faint" />} title="Couldn't load your tasks" text={error} />
    ) : (
      <div className="flex flex-1 items-center justify-center"><Loader2 className="animate-spin text-w-dim" /></div>
    )
  }
  const usage = usageLine(list.usage)
  if (list.tasks.length > 0) {
    return <div className="flex flex-1 items-center justify-center px-6 text-center text-xs text-w-dim">Open a task on the left.</div>
  }
  if (!tasksEnabled) {
    return (
      <Message
        icon={<Briefcase size={28} className="text-w-faint" />}
        title="Start a job search"
        text={'Say what you’re after (“COO roles across the US, mostly about salary, bonus and equity”). '
          + 'Espresso finds the postings, reads each one for pay and what the application asks, ranks them by what you '
          + 'care about, and drafts how to approach the best ones. Nothing is sent or submitted for you.'}
        footnote={usage}
        action={onNewJobSearch && (
          <button type="button" onClick={onNewJobSearch} className="rounded-md bg-w-accent px-3 py-1.5 text-xs font-semibold text-white hover:bg-w-accent-hi">New job search</button>
        )}
      />
    )
  }
  return (
    <Message
      icon={<ClipboardList size={28} className="text-w-faint" />}
      title="Give Espresso something to go and do"
      text={'“Find me a 1-bedroom in SF under $3,500 that allows dogs.” “The best organic lip balm under $15.” '
        + 'Espresso asks for anything it needs, works in the background, and keeps what it finds here with where each fact '
        + 'came from. Then refine it, ask for more, or turn it into a document.'}
      footnote={usage}
    />
  )
}

function Message({ icon, title, text, footnote, action }: {
  icon: React.ReactNode; title: string; text: string; footnote?: string | null; action?: React.ReactNode
}) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-2.5 px-6 text-center">
      {icon}
      <p className="text-sm font-semibold text-w-text">{title}</p>
      <p className="max-w-md text-xs leading-5 text-w-dim">{text}</p>
      {action}
      {footnote && <p className="text-[10px] text-w-dim">{footnote}</p>}
    </div>
  )
}
