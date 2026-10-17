import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import {
  cancelJobSearch, createJobSearch, deleteJobSearch, draftJobEmail, getJobLead, getJobSearch,
  getJobSearchStatus, listJobSearches, redraftJobApproach, rerankJobSearch, updateJobLead, widenJobSearch,
  type JobLeadDetail, type JobSearchCreate, type JobSearchDetail, type JobSearchList, type JobSearchSummary,
  type JobWeights,
} from '../../api/matchaWork/jobSearch'
import { errorCode, errorText, isLive, needsPolling, statusChanged } from './jobSearchLogic'

/** How often a running search (or a job being drafted) checks its cheap status. */
const POLL_MS = 5_000

/**
 * The Job search page's state: the person's searches, the open search and its
 * ranked jobs, and the open job. Like the macOS app, a live search polls its
 * cheap status every few seconds and reloads the jobs only when its
 * fingerprint, status or job count changes. The URL owns which search and job
 * are open; every answer is dropped if the person has moved on by the time it
 * arrives, and what is kept per search or per job is tagged with its id, so a
 * different one starts clean without resetting anything.
 */
export function useJobSearch(searchId: string | undefined, leadId: string | null) {
  const [list, setList] = useState<JobSearchList | null>(null)
  const [listError, setListError] = useState<string | null>(null)
  const [loadedDetail, setDetail] = useState<JobSearchDetail | null>(null)
  const [detailFailure, setDetailFailure] = useState<Tagged | null>(null)
  const [loadedLead, setLead] = useState<JobLeadDetail | null>(null)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<Tagged | null>(null)
  /** The job whose Draft email was refused because Gmail isn't connected. */
  const [notConnectedLead, setNotConnectedLead] = useState<string | null>(null)

  const detail = loadedDetail && loadedDetail.id === searchId ? loadedDetail : null
  const detailError = detailFailure && detailFailure.id === searchId ? detailFailure.message : null
  const lead = loadedLead && loadedLead.id === leadId ? loadedLead : null
  const error = failure && failure.id === searchId ? failure.message : null
  const emailNotConnected = !!leadId && notConnectedLead === leadId

  const searchRef = useRef(searchId)
  const leadRef = useRef(leadId)
  const detailRef = useRef(detail)
  const busyRef = useRef(false)
  // Before any effect below reads them.
  useLayoutEffect(() => {
    searchRef.current = searchId
    leadRef.current = leadId
    detailRef.current = detail
  })

  const setError = useCallback((message: string | null) => {
    setFailure(message === null ? null : { id: searchRef.current, message })
  }, [])

  const loadList = useCallback(() => listJobSearches().then(
    (loaded) => { setList(loaded); setListError(null) },
    (e: unknown) => { setListError(errorText(e, "Couldn't load your job searches.")) },
  ), [])

  /** A search as the server has it now: on screen if it's still the open one,
   *  and in the list either way. */
  const apply = useCallback((loaded: JobSearchDetail) => {
    if (searchRef.current === loaded.id) {
      setDetail(loaded)
      setDetailFailure(null)
    }
    setList((prev) => prev && { ...prev, searches: prev.searches.map((s) => (s.id === loaded.id ? loaded : s)) })
  }, [])

  const loadDetail = useCallback((id: string) => getJobSearch(id).then(
    apply,
    (e: unknown) => {
      if (searchRef.current === id) setDetailFailure({ id, message: errorText(e, "Couldn't load this job search.") })
    },
  ), [apply])

  const refreshLead = useCallback(async (id: string) => {
    const search = searchRef.current
    if (!search) return
    try {
      const loaded = await getJobLead(search, id)
      if (searchRef.current === search && leadRef.current === id) setLead(loaded)
    } catch (e) {
      if (leadRef.current === id) setError(errorText(e, "Couldn't load this job."))
    }
  }, [setError])

  useEffect(() => { void loadList() }, [loadList])

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
        const status = await getJobSearchStatus(searchId)
        if (searchRef.current !== searchId || !statusChanged(current, status)) return
        await loadDetail(searchId)
        if (leadRef.current) await refreshLead(leadRef.current)
        if (!isLive(status.status)) await loadList()
      } catch {
        // A missed poll is retried on the next tick.
      } finally {
        polling = false
      }
    }, POLL_MS)
    return () => window.clearInterval(timer)
  }, [searchId, loadDetail, refreshLead, loadList])

  const perform = useCallback(async (fallback: string, action: () => Promise<void>) => {
    if (busyRef.current) return
    busyRef.current = true
    setBusy(true)
    setError(null)
    try {
      await action()
    } catch (e) {
      setError(errorText(e, fallback))
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

  const setLeadState = useCallback((state: string, id: string) => {
    const search = searchRef.current
    if (!search) return Promise.resolve()
    return perform("Couldn't save that.", async () => {
      show(await updateJobLead(search, id, { user_state: state }))
      await loadDetail(search)
    })
  }, [perform, show, loadDetail])

  const saveNotes = useCallback((notes: string, id: string) => {
    const search = searchRef.current
    if (!search) return Promise.resolve()
    return perform("Couldn't save your notes.", async () => {
      show(await updateJobLead(search, id, { notes }))
    })
  }, [perform, show])

  const rerank = useCallback((weights: JobWeights) => {
    const search = searchRef.current
    if (!search) return Promise.resolve()
    return perform("Couldn't re-rank this search.", async () => { apply(await rerankJobSearch(search, weights)) })
  }, [perform, apply])

  /** Show the jobs that scored 3/5: the search reads and ranks them, and drafts nothing new. */
  const widen = useCallback(() => {
    const search = searchRef.current
    if (!search) return Promise.resolve()
    return perform("Couldn't add more jobs.", async () => { apply(await widenJobSearch(search)) })
  }, [perform, apply])

  const redraft = useCallback(() => {
    const search = searchRef.current
    const id = leadRef.current
    if (!search || !id) return Promise.resolve()
    return perform("Couldn't start drafting.", async () => {
      apply(await redraftJobApproach(search, id))
      await refreshLead(id)
    })
  }, [perform, apply, refreshLead])

  const cancel = useCallback(() => {
    const search = searchRef.current
    if (!search) return Promise.resolve()
    return perform("Couldn't cancel this search.", async () => { apply(await cancelJobSearch(search)) })
  }, [perform, apply])

  /** Delete a search. Resolves true once it's gone, so the page leaves it
   *  only then (a failure stays on screen, beside the search). */
  const remove = useCallback(async (id: string): Promise<boolean> => {
    let deleted = false
    await perform("Couldn't delete this search.", async () => {
      await deleteJobSearch(id)
      deleted = true
      setList((prev) => prev && { ...prev, searches: prev.searches.filter((s) => s.id !== id) })
      void loadList()
    })
    return deleted
  }, [perform, loadList])

  /** Put a job's first message in the person's Gmail drafts. Returns the
   *  draft's id (the same draft again while it is still in Gmail), or null. */
  const draftEmail = useCallback(async (id: string): Promise<string | null> => {
    const search = searchRef.current
    if (!search || busyRef.current) return null
    busyRef.current = true
    setBusy(true)
    setError(null)
    setNotConnectedLead(null)
    try {
      const result = await draftJobEmail(search, id)
      const updated = result.lead
      if (updated) {
        show(updated)
        setDetail((current) => current && current.id === search
          ? { ...current, leads: current.leads.map((l) => (l.id === id ? { ...l, ...pickSummary(updated) } : l)) }
          : current)
      }
      return result.draft_id
    } catch (e) {
      // Not connected is shown beside the button, with a way to Email.
      if (errorCode(e) === 'email_not_connected') setNotConnectedLead(id)
      else setError(errorText(e, "Couldn't put that in your Gmail drafts."))
      return null
    } finally {
      busyRef.current = false
      setBusy(false)
    }
  }, [show, setError])

  /** Start a search. Throws, so the form can keep the request id after a
   *  dropped connection (`retryIsNewRequest`). */
  const create = useCallback(async (body: JobSearchCreate): Promise<JobSearchSummary> => {
    const created = await createJobSearch(body)
    setList((prev) => prev && { ...prev, searches: [created, ...prev.searches.filter((s) => s.id !== created.id)] })
    void loadList()
    return created
  }, [loadList])

  return {
    list, listError, loadList,
    detail, detailError, loadDetail,
    lead,
    busy, error, setError, emailNotConnected,
    setLeadState, saveNotes, rerank, widen, redraft, cancel, remove, draftEmail, create,
  }
}

/** Something kept for one search, so another search doesn't show it. */
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
