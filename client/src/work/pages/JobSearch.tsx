import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { AlertTriangle, BookOpen, Briefcase, Loader2, Plus } from 'lucide-react'
import { useMe } from '../../hooks/useMe'
import { useWorkBase } from '../routes/WorkSurfaceContext'
import type { JobLeadDetail, JobSearchList, JobSearchSummary } from '../api/matchaWork/jobSearch'
import { askEspressoPrompt, canDraft, displayTitle, isLive, statusLabel, usageLine } from './JobSearch/jobSearchLogic'
import { useJobSearch } from './JobSearch/useJobSearch'
import SearchDetail from './JobSearch/SearchDetail'
import LeadPane from './JobSearch/LeadPane'
import NewJobSearchModal from './JobSearch/NewJobSearchModal'
import JobSearchGuide, { JOB_SEARCH_GUIDE_SEEN_KEY } from './JobSearch/JobSearchGuide'
import type { AssistantDraftState } from './Assistant'

function guideSeen(): boolean {
  try { return localStorage.getItem(JOB_SEARCH_GUIDE_SEEN_KEY) === '1' } catch { return true }
}

/**
 * Espresso Job search on the web: the person's searches on the left, the open
 * search's ranked jobs in the middle, and the open job on the right. The same
 * searches, API and rules as the macOS app's Job search. Personal accounts only.
 */
export default function JobSearch() {
  const { isPersonal } = useMe()
  if (!isPersonal) {
    return <p className="p-6 text-sm text-w-dim">Job search comes with a personal Espresso account.</p>
  }
  return <JobSearchPage />
}

function JobSearchPage() {
  const base = useWorkBase()
  const navigate = useNavigate()
  const { searchId } = useParams<{ searchId?: string }>()
  const [params, setParams] = useSearchParams()
  const leadId = params.get('job')
  const js = useJobSearch(searchId, leadId)
  const [creating, setCreating] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)
  const [guideDone, setGuideDone] = useState(guideSeen)
  const [draftedLeadId, setDraftedLeadId] = useState<string | null>(null)
  const { detail, list } = js
  const guideOpen = helpOpen || (list !== null && !guideDone && !creating)

  const setLeadParam = useCallback((id: string | null) => {
    setParams((prev) => {
      const next = new URLSearchParams(prev)
      if (id) next.set('job', id)
      else next.delete('job')
      return next
    }, { replace: !!leadId })
  }, [setParams, leadId])

  function selectLead(id: string | null) {
    setDraftedLeadId(null)
    setLeadParam(id)
  }

  // A job that is no longer in the search (deleted, or a stale link) closes.
  useEffect(() => {
    if (detail && leadId && !detail.leads.some((l) => l.id === leadId)) setLeadParam(null)
  }, [detail, leadId, setLeadParam])

  function closeGuide() {
    try { localStorage.setItem(JOB_SEARCH_GUIDE_SEEN_KEY, '1') } catch { /* best effort */ }
    setHelpOpen(false)
    setGuideDone(true)
  }

  function openSearch(id: string) {
    navigate(`${base}/jobs/${id}`)
  }

  async function removeSearch() {
    if (!detail) return
    if (!window.confirm('Delete this search? Its jobs and drafts are removed, but it still counts for the month.')) return
    if (await js.remove(detail.id)) navigate(`${base}/jobs`)
  }

  /** `existingOnly` is Edit draft: it finds the draft in Gmail and never makes one. */
  async function draftEmail(id: string, existingOnly = false) {
    const draft = await js.draftEmail(id, existingOnly)
    setDraftedLeadId(draft ? id : null)
  }

  function askEspresso(lead: JobLeadDetail) {
    if (!searchId) return
    const state: AssistantDraftState = { draft: { id: Date.now(), text: askEspressoPrompt(searchId, lead.id) } }
    navigate(`${base}/assistant`, { state })
  }

  return (
    <div className="flex h-full min-h-0">
      <SearchList
        list={list}
        error={js.listError}
        selectedId={searchId ?? null}
        hiddenOnSmall={!!searchId}
        onOpen={openSearch}
        onNew={() => setCreating(true)}
        onHelp={() => setHelpOpen(true)}
        onRetry={() => void js.loadList()}
      />

      <main className={`min-h-0 min-w-0 flex-1 flex-col ${searchId ? 'flex' : 'hidden md:flex'}`}>
        {!searchId ? (
          <EmptyState hasSearches={!!list?.searches.length} onNew={() => setCreating(true)} onHelp={() => setHelpOpen(true)} />
        ) : detail ? (
          <SearchDetail
            key={detail.id}
            detail={detail}
            busy={js.busy}
            error={js.error}
            onDismissError={() => js.setError(null)}
            selectedLeadId={leadId}
            onSelectLead={(id) => selectLead(id)}
            onRerank={(w) => void js.rerank(w)}
            onWiden={() => void js.widen()}
            onCancel={() => void js.cancel()}
            onDelete={() => void removeSearch()}
            onBack={() => navigate(`${base}/jobs`)}
          />
        ) : js.detailError ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
            <AlertTriangle size={28} className="text-w-faint" />
            <p className="text-sm font-semibold text-w-text">Couldn't load this job search</p>
            <p className="max-w-md text-xs text-w-dim">{js.detailError}</p>
            <button type="button" onClick={() => void js.loadDetail(searchId)} className="rounded-md bg-w-accent px-3 py-1.5 text-xs font-semibold text-white hover:bg-w-accent-hi">
              Try again
            </button>
          </div>
        ) : (
          <div className="flex flex-1 items-center justify-center"><Loader2 className="animate-spin text-w-dim" /></div>
        )}
      </main>

      {leadId && detail && (
        <LeadPane
          lead={js.lead}
          loadError={js.leadLoadError}
          error={js.leadError}
          canDraft={canDraft(detail)}
          busy={js.busy}
          emailNotConnected={js.emailNotConnected}
          emailDrafted={draftedLeadId === leadId}
          emailDraftGone={js.emailDraftGone}
          emailPath={`${base}/email`}
          onClose={() => selectLead(null)}
          onRetry={() => void js.reloadLead()}
          onDismissError={() => js.setLeadError(null)}
          onSetState={(state, id) => void js.setLeadState(state, id)}
          onSaveNotes={(notes, id) => void js.saveNotes(notes, id)}
          onRedraft={() => void js.redraft()}
          onDraftEmail={(id) => void draftEmail(id)}
          onEditDraft={(id) => void draftEmail(id, true)}
          onAskEspresso={askEspresso}
        />
      )}

      {creating && (
        <NewJobSearchModal
          list={list}
          onCreate={js.create}
          onCreated={(search) => { setCreating(false); openSearch(search.id) }}
          onClose={() => setCreating(false)}
        />
      )}
      {guideOpen && <JobSearchGuide onClose={closeGuide} />}
    </div>
  )
}

function SearchList({ list, error, selectedId, hiddenOnSmall, onOpen, onNew, onHelp, onRetry }: {
  list: JobSearchList | null
  error: string | null
  selectedId: string | null
  hiddenOnSmall: boolean
  onOpen: (id: string) => void
  onNew: () => void
  onHelp: () => void
  onRetry: () => void
}) {
  const usage = usageLine(list?.usage)
  return (
    <aside className={`min-h-0 w-full shrink-0 flex-col border-r border-w-line bg-w-surface md:w-72 ${hiddenOnSmall ? 'hidden md:flex' : 'flex'}`}>
      <div className="space-y-2 border-b border-w-line px-4 py-3">
        <div className="flex items-center gap-2">
          <Briefcase size={15} className="text-w-accent" />
          <h1 className="flex-1 text-sm font-semibold text-w-text">Job search</h1>
          <button type="button" onClick={onHelp} className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-[11px] text-w-dim hover:bg-w-surface2 hover:text-w-text">
            <BookOpen size={12} /> How it works
          </button>
        </div>
        <button type="button" onClick={onNew} className="flex w-full items-center justify-center gap-1.5 rounded-md bg-w-accent px-3 py-1.5 text-xs font-semibold text-white hover:bg-w-accent-hi">
          <Plus size={13} /> New search
        </button>
        {usage && <p className="text-center text-[10px] text-w-dim">{usage}</p>}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {error && !list ? (
          <div className="space-y-2 p-3 text-center">
            <p className="text-xs text-w-dim">{error}</p>
            <button type="button" onClick={onRetry} className="text-xs font-semibold text-w-accent hover:underline">Try again</button>
          </div>
        ) : !list ? (
          <div className="flex justify-center p-6"><Loader2 size={16} className="animate-spin text-w-dim" /></div>
        ) : list.searches.length === 0 ? (
          <p className="p-3 text-center text-xs leading-5 text-w-dim">Your searches show up here.</p>
        ) : (
          <ul className="space-y-0.5">
            {list.searches.map((search) => (
              <li key={search.id}>
                <SearchRow search={search} selected={search.id === selectedId} onOpen={onOpen} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  )
}

function SearchRow({ search, selected, onOpen }: { search: JobSearchSummary; selected: boolean; onOpen: (id: string) => void }) {
  const live = isLive(search.status)
  const facts = [
    live || search.status === 'failed' || search.status === 'cancelled' ? statusLabel(search.status) : null,
    search.lead_count > 0 ? `${search.lead_count} ${search.lead_count === 1 ? 'job' : 'jobs'}` : null,
    search.created_at ? new Date(search.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : null,
  ].filter(Boolean)
  return (
    <button
      type="button"
      onClick={() => onOpen(search.id)}
      aria-current={selected ? 'page' : undefined}
      className={`w-full rounded-md px-2.5 py-2 text-left ${selected ? 'bg-w-surface2' : 'hover:bg-w-surface2/60'}`}
    >
      <p className="truncate text-xs font-medium text-w-text">{displayTitle(search)}</p>
      <p className={`mt-0.5 flex items-center gap-1 truncate text-[10px] ${search.status === 'failed' ? 'text-amber-500' : 'text-w-dim'}`}>
        {live && <Loader2 size={9} className="shrink-0 animate-spin" />}
        {facts.join(' · ')}
      </p>
    </button>
  )
}

function EmptyState({ hasSearches, onNew, onHelp }: { hasSearches: boolean; onNew: () => void; onHelp: () => void }) {
  if (hasSearches) {
    return (
      <div className="flex flex-1 items-center justify-center px-6 text-center text-xs text-w-dim">
        Open a search on the left, or start a new one.
      </div>
    )
  }
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-2xl border border-w-line bg-w-surface2/70">
        <Briefcase size={20} className="text-w-accent" />
      </span>
      <h2 className="text-base font-semibold text-w-text">A serious search from one sentence</h2>
      <p className="max-w-md text-xs leading-5 text-w-dim">
        Tell Espresso what you're after. It searches live job listings, ranks them by what matters to you, and drafts
        how to go after the best ones. Pay is only ever what a posting states, and nothing is sent for you.
      </p>
      <div className="flex items-center gap-3">
        <button type="button" onClick={onNew} className="inline-flex items-center gap-1.5 rounded-md bg-w-accent px-3 py-1.5 text-xs font-semibold text-white hover:bg-w-accent-hi">
          <Plus size={13} /> Start a search
        </button>
        <button type="button" onClick={onHelp} className="text-xs text-w-dim hover:text-w-text">How it works</button>
      </div>
    </div>
  )
}
