import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, Loader2 } from 'lucide-react'
import { useWorkBase } from '../../routes/WorkSurfaceContext'
import type { JobLeadDetail } from '../../api/matchaWork/jobSearch'
import { askEspressoPrompt, canDraft, JOB_SEARCH_GUIDE_SEEN_KEY } from '../JobSearch/jobSearchLogic'
import { useJobSearch } from '../JobSearch/useJobSearch'
import SearchDetail from '../JobSearch/SearchDetail'
import LeadPane from '../JobSearch/LeadPane'
import JobSearchGuide from '../JobSearch/JobSearchGuide'
import type { AssistantDraftState } from '../Assistant'

function guideSeen(): boolean {
  try { return localStorage.getItem(JOB_SEARCH_GUIDE_SEEN_KEY) === '1' } catch { return true }
}

/** A job-search task's own view, including its job pane, inside Tasks. */
export default function JobSearchPane({
  searchId, leadId, onSelectLead, onBack, onDelete, onChanged, guideBlocked, deleting, deleteError, onDismissDeleteError,
}: {
  searchId: string
  leadId: string | null
  onSelectLead: (id: string | null) => void
  onBack: () => void
  onDelete: () => void
  onChanged: () => Promise<unknown>
  guideBlocked: boolean
  deleting: boolean
  deleteError: string | null
  onDismissDeleteError: () => void
}) {
  const base = useWorkBase()
  const navigate = useNavigate()
  const js = useJobSearch(searchId, leadId, { list: false, mutationsDisabled: deleting })
  const [helpOpen, setHelpOpen] = useState(false)
  const [guideDone, setGuideDone] = useState(guideSeen)
  const [draftedLeadId, setDraftedLeadId] = useState<string | null>(null)
  const { detail } = js
  const guideOpen = !guideBlocked && (helpOpen || (!!detail && !guideDone))

  // Defer the list refresh out of the effect's synchronous work. The search
  // owns its polling; Tasks only needs to follow its status in the rail.
  const status = detail?.status
  useEffect(() => {
    if (!status) return
    let cancelled = false
    void Promise.resolve().then(() => { if (!cancelled) return onChanged() })
    return () => { cancelled = true }
  }, [status, onChanged])

  // A job no longer in this search (a stale link) closes.
  useEffect(() => {
    if (detail && leadId && !detail.leads.some((lead) => lead.id === leadId)) onSelectLead(null)
  }, [detail, leadId, onSelectLead])

  function selectLead(id: string | null) {
    setDraftedLeadId(null)
    onSelectLead(id)
  }

  function closeGuide() {
    try { localStorage.setItem(JOB_SEARCH_GUIDE_SEEN_KEY, '1') } catch { /* best effort */ }
    setHelpOpen(false)
    setGuideDone(true)
  }

  /** Edit draft finds the existing Gmail draft and never makes another. */
  async function draftEmail(id: string, existingOnly = false) {
    const draft = await js.draftEmail(id, existingOnly)
    setDraftedLeadId(draft ? id : null)
  }

  function askEspresso(lead: JobLeadDetail) {
    const state: AssistantDraftState = { draft: { id: Date.now(), text: askEspressoPrompt(searchId, lead.id) } }
    navigate(`${base}/assistant`, { state })
  }

  return (
    <div className="flex min-h-0 min-w-0 flex-1">
      {detail ? (
        <SearchDetail
          key={detail.id}
          detail={detail}
          busy={js.busy || deleting}
          error={js.error ?? deleteError}
          onDismissError={() => { js.setError(null); onDismissDeleteError() }}
          selectedLeadId={leadId}
          onSelectLead={selectLead}
          onRerank={(weights) => void js.rerank(weights)}
          onWiden={() => void js.widen()}
          onCancel={() => void js.cancel()}
          onDelete={onDelete}
          onBack={onBack}
          onHelp={() => setHelpOpen(true)}
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

      {leadId && detail && (
        <LeadPane
          lead={js.lead}
          loadError={js.leadLoadError}
          error={js.leadError}
          canDraft={canDraft(detail)}
          busy={js.busy || deleting}
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
      {guideOpen && <JobSearchGuide onClose={closeGuide} />}
    </div>
  )
}
