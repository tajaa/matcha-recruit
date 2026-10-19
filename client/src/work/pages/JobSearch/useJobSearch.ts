import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { ApiError } from '../../../api/client'
import {
  cancelJobSearch, draftJobEmail, getJobLead, getJobSearch, getJobSearchStatus, redraftJobApproach,
  rerankJobSearch, updateJobLead, widenJobSearch, type JobLeadDetail, type JobSearchDetail, type JobWeights,
} from '../../api/matchaWork/jobSearch'
import { errorCode, errorLead, errorText, needsPolling, statusChanged } from './jobSearchLogic'

/** How often a running search (or a job being drafted) checks its cheap status. */
const POLL_MS = 5_000

/** The search was deleted (from the Mac, the assistant) or isn't this person's:
 *  asking again won't bring it back. */
const isGone = (e: unknown) => e instanceof ApiError && (e.status === 404 || e.status === 403)
const GONE = 'This job search is no longer available. It may have been deleted.'

/**
 * A job-search task's state: the open search and its ranked jobs, and the open
 * job (Tasks lists, starts and deletes searches). Like the macOS app, a live
 * search polls its cheap status every few seconds and reloads the jobs only
 * when its fingerprint, status or job count changes. The URL owns which search and job
 * are open; every answer is dropped if the person has moved on by the time it
 * arrives, and what is kept per search or per job is tagged with its id, so a
 * different one starts clean without resetting anything.
 *
 * Reads are numbered, per kind (the open search, the open job). An
 * answer is kept only if nothing newer was asked since: neither a later read
 * nor a change the person made. A change takes a number when it starts and
 * again when its answer lands, so a read that left before Redraft can't put
 * the old finished search back (and stop the polling), and a job read that
 * left before Mark Saved can't undo it. Only reads of what is still open are
 * dropped: a search or job opened while a change was out loads as usual.
 */
export function useJobSearch(
  searchId: string | undefined, leadId: string | null, { mutationsDisabled = false } = {},
) {
  const [loadedDetail, setDetail] = useState<JobSearchDetail | null>(null)
  const [detailFailure, setDetailFailure] = useState<Tagged | null>(null)
  const [loadedLead, setLead] = useState<JobLeadDetail | null>(null)
  const [leadLoadFailure, setLeadLoadFailure] = useState<Tagged | null>(null)
  const [leadFailure, setLeadFailure] = useState<Tagged | null>(null)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<Tagged | null>(null)
  /** Why the open job's first message didn't reach Gmail drafts: Gmail isn't
   *  connected, or its draft left Gmail (sent or deleted there). */
  const [emailIssue, setEmailIssue] = useState<{ id: string; kind: 'not_connected' | 'draft_gone' } | null>(null)

  const detail = loadedDetail && loadedDetail.id === searchId ? loadedDetail : null
  const detailError = detailFailure && detailFailure.id === searchId ? detailFailure.message : null
  const lead = loadedLead && loadedLead.id === leadId ? loadedLead : null
  const leadLoadError = !lead && leadLoadFailure && leadLoadFailure.id === leadId ? leadLoadFailure.message : null
  const leadError = leadFailure && leadFailure.id === leadId ? leadFailure.message : null
  const error = failure && failure.id === searchId ? failure.message : null
  const issue = leadId && emailIssue && emailIssue.id === leadId ? emailIssue.kind : null

  const searchRef = useRef(searchId)
  const leadRef = useRef(leadId)
  const detailRef = useRef(detail)
  const shownLeadRef = useRef<string | null>(lead?.id ?? null)
  const busyRef = useRef(false)
  // Deleting the owning task holds changes, including callbacks retained by
  // a menu opened before deletion began. Reads may continue until unmount.
  const mutationsDisabledRef = useRef(mutationsDisabled)
  const detailSeq = useRef(0)
  const leadSeq = useRef(0)
  // Before any effect below reads them.
  useLayoutEffect(() => {
    searchRef.current = searchId
    leadRef.current = leadId
    detailRef.current = detail
    shownLeadRef.current = lead?.id ?? null
    mutationsDisabledRef.current = mutationsDisabled
  })

  const setError = useCallback((message: string | null) => {
    setFailure(message === null ? null : { id: searchRef.current, message })
  }, [])

  const setLeadError = useCallback((message: string | null) => {
    setLeadFailure(message === null ? null : { id: leadRef.current ?? undefined, message })
  }, [])

  /** A change to `search` (and the job `lead`) is starting or has landed:
   *  reads of them already on their way are older than it, so their answers
   *  are dropped. Reads of a search or job opened since are left alone. */
  const supersede = useCallback((search: string | null, lead: string | null = null) => {
    if (search && searchRef.current === search) detailSeq.current += 1
    if (lead && leadRef.current === lead) leadSeq.current += 1
  }, [])

  /** A search as the server has it now, on screen if it's still the open one. */
  const apply = useCallback((loaded: JobSearchDetail) => {
    if (searchRef.current === loaded.id) {
      setDetail(loaded)
      setDetailFailure(null)
    }
  }, [])

  const loadDetail = useCallback((id: string) => {
    const seq = ++detailSeq.current
    return getJobSearch(id).then(
      (loaded) => { if (seq === detailSeq.current) apply(loaded) },
      (e: unknown) => {
        if (seq === detailSeq.current && searchRef.current === id) {
          setDetailFailure({ id, message: errorText(e, "Couldn't load this job search.") })
        }
      },
    )
  }, [apply])

  /** The open job again. A failure is shown in its pane only when there is
   *  nothing of it on screen; a background refresh that misses keeps what's there. */
  const refreshLead = useCallback(async (id: string) => {
    const search = searchRef.current
    if (!search) return
    const seq = ++leadSeq.current
    setLeadLoadFailure((f) => (f && f.id === id ? null : f))
    try {
      const loaded = await getJobLead(search, id)
      if (seq === leadSeq.current && searchRef.current === search && leadRef.current === id) setLead(loaded)
    } catch (e) {
      if (seq === leadSeq.current && leadRef.current === id && shownLeadRef.current !== id) {
        setLeadLoadFailure({ id, message: errorText(e, "Couldn't load this job.") })
      }
    }
  }, [])

  useEffect(() => {
    if (searchId) void loadDetail(searchId)
  }, [searchId, loadDetail])

  useEffect(() => {
    if (leadId && searchId) void refreshLead(leadId)
  }, [searchId, leadId, refreshLead])

  // The poll: cheap status, full reload only on a change.
  useEffect(() => {
    if (!searchId) return
    let polling = false
    const timer = window.setInterval(async () => {
      const current = detailRef.current
      if (polling || document.hidden || !current || current.id !== searchId || !needsPolling(current)) return
      polling = true
      try {
        const asked = detailSeq.current
        const status = await getJobSearchStatus(searchId)
        // Something newer than this status landed while it was out: the next tick looks again.
        if (searchRef.current !== searchId || detailSeq.current !== asked || !statusChanged(current, status)) return
        await loadDetail(searchId)
        if (leadRef.current) await refreshLead(leadRef.current)
      } catch (e) {
        // Gone for good: stop asking and say so. Anything else is retried on
        // the next tick.
        if (isGone(e) && searchRef.current === searchId) {
          detailSeq.current += 1
          setDetail(null)
          setDetailFailure({ id: searchId, message: GONE })
        }
      } finally {
        polling = false
      }
    }, POLL_MS)
    return () => window.clearInterval(timer)
  }, [searchId, loadDetail, refreshLead])

  /** One change at a time. A change made from a job's pane reports there
   *  (`fromLead`), since below the widest layout the pane covers the search. */
  const perform = useCallback(async (fallback: string, action: () => Promise<void>, fromLead?: string) => {
    if (busyRef.current || mutationsDisabledRef.current) return
    busyRef.current = true
    setBusy(true)
    setError(null)
    setLeadFailure(null)
    try {
      await action()
    } catch (e) {
      const message = errorText(e, fallback)
      if (fromLead) setLeadFailure({ id: fromLead, message })
      else setError(message)
    } finally {
      busyRef.current = false
      setBusy(false)
    }
  }, [setError])

  /** A save's answer replaces the open job only if that job is still open:
   *  clicking another job while it saved must not put the old one back. */
  const show = useCallback((updated: JobLeadDetail) => {
    if (leadRef.current === updated.id) setLead(updated)
  }, [])

  /** Change a search (and the job `lead`, for a redraft): drop older reads,
   *  then keep what the change returned. */
  const change = useCallback(async (search: string, request: () => Promise<JobSearchDetail>, lead: string | null = null) => {
    supersede(search, lead)
    let updated: JobSearchDetail
    try {
      updated = await request()
    } catch (e) {
      // A 409 means the search moved on elsewhere (widened or redrafted from
      // the Mac): read it again, so its status shows and polling resumes.
      if (e instanceof ApiError && e.status === 409) void loadDetail(search)
      throw e
    }
    supersede(search, lead)
    apply(updated)
  }, [supersede, apply, loadDetail])

  /** Change a job: drop older reads of it, then show what the save returned. */
  const changeLead = useCallback(async (id: string, request: () => Promise<JobLeadDetail>) => {
    supersede(null, id)
    const updated = await request()
    supersede(null, id)
    show(updated)
  }, [supersede, show])

  const setLeadState = useCallback((state: string, id: string) => {
    const search = searchRef.current
    if (!search) return Promise.resolve()
    return perform("Couldn't save that.", async () => {
      await changeLead(id, () => updateJobLead(search, id, { user_state: state }))
      await loadDetail(search)
    }, id)
  }, [perform, changeLead, loadDetail])

  const saveNotes = useCallback((notes: string, id: string) => {
    const search = searchRef.current
    if (!search) return Promise.resolve()
    return perform("Couldn't save your notes.", async () => {
      await changeLead(id, () => updateJobLead(search, id, { notes }))
    }, id)
  }, [perform, changeLead])

  const rerank = useCallback((weights: JobWeights) => {
    const search = searchRef.current
    if (!search) return Promise.resolve()
    return perform("Couldn't re-rank this search.", () => change(search, () => rerankJobSearch(search, weights)))
  }, [perform, change])

  /** Show the jobs that scored 3/5: the search reads and ranks them, and drafts nothing new. */
  const widen = useCallback(() => {
    const search = searchRef.current
    if (!search) return Promise.resolve()
    return perform("Couldn't add more jobs.", () => change(search, () => widenJobSearch(search)))
  }, [perform, change])

  const redraft = useCallback(() => {
    const search = searchRef.current
    const id = leadRef.current
    if (!search || !id) return Promise.resolve()
    return perform("Couldn't start drafting.", async () => {
      await change(search, () => redraftJobApproach(search, id), id)
      await refreshLead(id)
    }, id)
  }, [perform, change, refreshLead])

  const cancel = useCallback(() => {
    const search = searchRef.current
    if (!search) return Promise.resolve()
    const id = leadRef.current
    return perform("Couldn't cancel this search.", async () => {
      await change(search, () => cancelJobSearch(search))
      // Cancel marks the jobs still waiting for a draft failed: the open one
      // would otherwise keep saying it is drafting, with no poll to correct it.
      if (id) await refreshLead(id)
    })
  }, [perform, change, refreshLead])

  /** The job as the server has it after a Draft email or Edit draft: in its
   *  pane, and in its row of the search. */
  const landEmail = useCallback((search: string, updated: JobLeadDetail | null) => {
    if (!updated) return
    supersede(search, updated.id)
    show(updated)
    setDetail((current) => current && current.id === search
      ? { ...current, leads: current.leads.map((l) => (l.id === updated.id ? { ...l, ...pickSummary(updated) } : l)) }
      : current)
  }, [supersede, show])

  /** Put a job's first message in the person's Gmail drafts. Returns the
   *  draft's id (the same draft again while it is still in Gmail), or null.
   *  `existingOnly` is Edit draft: it never makes a draft, and a draft that
   *  left Gmail (sent or deleted there) is said in the pane, with Draft email
   *  to make a new one. Nothing is ever sent. */
  const draftEmail = useCallback(async (id: string, existingOnly = false): Promise<string | null> => {
    const search = searchRef.current
    let draft: string | null = null
    if (!search) return draft
    await perform("Couldn't put that in your Gmail drafts.", async () => {
      setEmailIssue(null)
      supersede(search, id)
      try {
        const result = await draftJobEmail(search, id, existingOnly)
        landEmail(search, result.lead)
        draft = result.draft_id
      } catch (e) {
        const code = errorCode(e)
        if (code === 'email_not_connected') setEmailIssue({ id, kind: 'not_connected' })
        else if (code === 'email_draft_missing') {
          landEmail(search, errorLead(e))
          setEmailIssue({ id, kind: 'draft_gone' })
        } else throw e
      }
    }, id)
    return draft
  }, [perform, supersede, landEmail])

  return {
    detail, detailError, loadDetail,
    lead, leadLoadError, leadError, setLeadError,
    reloadLead: () => (leadRef.current ? refreshLead(leadRef.current) : Promise.resolve()),
    busy, error, setError,
    emailNotConnected: issue === 'not_connected',
    emailDraftGone: issue === 'draft_gone',
    setLeadState, saveNotes, rerank, widen, redraft, cancel, draftEmail,
  }
}

/** Something kept for one search or job, so another doesn't show it. */
type Tagged = { id: string | undefined; message: string }

/** The summary fields of a job, for its row in the list. */
function pickSummary(lead: JobLeadDetail) {
  return {
    user_state: lead.user_state,
    approach_status: lead.approach_status,
    email_draft_id: lead.email_draft_id,
    email_drafted_at: lead.email_drafted_at,
    email_sent_at: lead.email_sent_at,
  }
}
