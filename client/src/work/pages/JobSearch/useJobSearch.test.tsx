import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../../api/client'
import { useJobSearch } from './useJobSearch'
import type { JobLeadDetail, JobSearchDetail, JobSearchList } from '../../api/matchaWork/jobSearch'

const mock = vi.hoisted(() => ({
  list: vi.fn(), get: vi.fn(), status: vi.fn(), lead: vi.fn(), update: vi.fn(), redraft: vi.fn(), rerank: vi.fn(),
  email: vi.fn(),
}))
vi.mock('../../api/matchaWork/jobSearch', () => ({
  listJobSearches: mock.list,
  getJobSearch: mock.get,
  getJobSearchStatus: mock.status,
  getJobLead: mock.lead,
  updateJobLead: mock.update,
  redraftJobApproach: mock.redraft,
  rerankJobSearch: mock.rerank,
  draftJobEmail: mock.email,
  widenJobSearch: vi.fn(),
  cancelJobSearch: vi.fn(),
  deleteJobSearch: vi.fn(),
  createJobSearch: vi.fn(),
}))

const job = (over: Partial<JobLeadDetail> = {}): JobLeadDetail => ({
  id: 'l1', title: 'COO', company: 'Acme', location: 'Austin, TX', remote: null, source_url: null, apply_url: null,
  posted_text: null, comp_line: '$250K', comp_status: 'posted', fit_score: 4, screen_status: 'relevant', rank: 1,
  rank_band: 0, flags: [], user_state: 'new', approach_status: 'done', email_draft_id: null, email_drafted_at: null,
  email_sent_at: null, description: '', comp: null, pay_law_hint: null, screen_reason: null, fit_reasons: [],
  approach: null, notes: '', ...over,
})

const search = (over: Partial<JobSearchDetail> = {}): JobSearchDetail => ({
  id: 's1', title: 'COO', ask: 'COO roles', status: 'done', progress: null, error: null, lead_count: 1,
  posted_pay_count: 1, weights: null, use_resume: false, created_at: null, fit_floor: 4, fingerprint: 'f1',
  leads: [job()], ...over,
})

const searches = (...rows: JobSearchDetail[]): JobSearchList => ({ searches: rows, usage: null, consent: null, available: true })

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => { resolve = r })
  return { promise, resolve }
}

async function opened(leadId: string | null, searchId = 's1') {
  mock.list.mockResolvedValue(searches(search()))
  const hook = renderHook(({ s, l }) => useJobSearch(s, l), { initialProps: { s: searchId as string | undefined, l: leadId } })
  await act(async () => {})
  return hook
}

describe('useJobSearch reads and changes', () => {
  it("doesn't let a read that left before Redraft put the finished search back", async () => {
    mock.get.mockResolvedValueOnce(search())
    mock.lead.mockResolvedValue(job())
    const { result } = await opened('l1')
    expect(result.current.detail?.status).toBe('done')

    const old = deferred<JobSearchDetail>()
    mock.get.mockReturnValueOnce(old.promise)
    let reading = Promise.resolve()
    act(() => { reading = result.current.loadDetail('s1') })
    mock.redraft.mockResolvedValue(search({ status: 'approaching', fingerprint: 'f2' }))
    await act(async () => { await result.current.redraft() })
    expect(result.current.detail?.status).toBe('approaching')

    await act(async () => { old.resolve(search()); await reading })
    expect(result.current.detail?.status).toBe('approaching') // still live, so it keeps polling
  })

  it("doesn't let a job read that left before Mark Saved undo it", async () => {
    mock.get.mockResolvedValue(search())
    mock.lead.mockResolvedValueOnce(job())
    const { result } = await opened('l1')
    expect(result.current.lead?.user_state).toBe('new')

    const old = deferred<JobLeadDetail>()
    mock.lead.mockReturnValueOnce(old.promise)
    let reading = Promise.resolve()
    act(() => { reading = result.current.reloadLead() })
    mock.update.mockResolvedValue(job({ user_state: 'saved' }))
    await act(async () => { await result.current.setLeadState('saved', 'l1') })
    expect(result.current.lead?.user_state).toBe('saved')

    await act(async () => { old.resolve(job()); await reading })
    expect(result.current.lead?.user_state).toBe('saved')
  })

  it('keeps only the newest of two reads of the same search', async () => {
    mock.get.mockResolvedValueOnce(search())
    const { result } = await opened(null)
    const first = deferred<JobSearchDetail>()
    const second = deferred<JobSearchDetail>()
    mock.get.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    let a = Promise.resolve()
    let b = Promise.resolve()
    act(() => { a = result.current.loadDetail('s1'); b = result.current.loadDetail('s1') })
    await act(async () => { second.resolve(search({ fingerprint: 'new' })); await b })
    await act(async () => { first.resolve(search({ fingerprint: 'old' })); await a })
    expect(result.current.detail?.fingerprint).toBe('new')
  })

  it('loads a job opened while a change to another was out', async () => {
    mock.get.mockResolvedValue(search({ leads: [job(), job({ id: 'l2' })] }))
    mock.lead.mockResolvedValueOnce(job())
    const { result, rerender } = await opened('l1')

    const saving = deferred<JobLeadDetail>()
    mock.update.mockReturnValueOnce(saving.promise)
    let saved = Promise.resolve()
    act(() => { saved = result.current.setLeadState('saved', 'l1') })
    const other = deferred<JobLeadDetail>()
    mock.lead.mockReturnValueOnce(other.promise)
    rerender({ s: 's1', l: 'l2' })
    await act(async () => { saving.resolve(job({ user_state: 'saved' })); await saved })
    await act(async () => { other.resolve(job({ id: 'l2', title: 'Chief Operating Officer' })) })
    expect(result.current.lead?.title).toBe('Chief Operating Officer')
  })

  it('asks for the list again when a change lands while a list read is out', async () => {
    mock.get.mockResolvedValue(search())
    const { result } = await opened(null)
    const old = deferred<JobSearchList>()
    mock.list.mockReturnValueOnce(old.promise)
    let reading = Promise.resolve()
    act(() => { reading = result.current.loadList() })
    mock.rerank.mockResolvedValue(search({ status: 'enriching' }))
    mock.list.mockResolvedValueOnce(searches(search({ status: 'enriching' })))
    await act(async () => { await result.current.rerank({ base: 1, bonus: 0, equity: 0, fit: 0 }) })
    await act(async () => { old.resolve(searches(search())); await reading })
    expect(mock.list).toHaveBeenCalledTimes(3)
    expect(result.current.list?.searches[0].status).toBe('enriching')
  })
})

describe('useJobSearch job errors', () => {
  it("says a job couldn't load, with no search-wide error, and clears it on a retry", async () => {
    mock.get.mockResolvedValue(search())
    mock.lead.mockRejectedValueOnce(new ApiError('Job not found.', 404, {}))
    const { result } = await opened('l1')
    expect(result.current.lead).toBeNull()
    expect(result.current.leadLoadError).toBe('Job not found.')
    expect(result.current.error).toBeNull()

    mock.lead.mockResolvedValueOnce(job())
    await act(async () => { await result.current.reloadLead() })
    expect(result.current.leadLoadError).toBeNull()
    expect(result.current.lead?.title).toBe('COO')

    // A refresh that misses while it's on screen keeps what's there.
    mock.lead.mockRejectedValueOnce(new Error('offline'))
    await act(async () => { await result.current.reloadLead() })
    expect(result.current.lead?.title).toBe('COO')
    expect(result.current.leadLoadError).toBeNull()
    expect(result.current.error).toBeNull()
  })

  it("reports what the job's pane did in the pane, and the search's own changes on the search", async () => {
    mock.get.mockResolvedValue(search())
    mock.lead.mockResolvedValue(job())
    const { result } = await opened('l1')

    mock.update.mockRejectedValueOnce(new ApiError('Too many changes.', 429, {}))
    await act(async () => { await result.current.setLeadState('saved', 'l1') })
    expect(result.current.leadError).toBe('Too many changes.')
    expect(result.current.error).toBeNull()

    mock.update.mockRejectedValueOnce(new Error('offline'))
    await act(async () => { await result.current.saveNotes('Call Jane', 'l1') })
    expect(result.current.leadError).toBe("Couldn't save your notes.")

    mock.redraft.mockRejectedValueOnce(new ApiError('Redrafts are capped for this search.', 429, {}))
    await act(async () => { await result.current.redraft() })
    expect(result.current.leadError).toBe('Redrafts are capped for this search.')

    mock.email.mockRejectedValueOnce(new ApiError('Gmail refused the draft.', 502, {}))
    await act(async () => { await result.current.draftEmail('l1') })
    expect(result.current.leadError).toBe('Gmail refused the draft.')
    expect(result.current.error).toBeNull()

    mock.rerank.mockRejectedValueOnce(new ApiError('Re-rank failed.', 500, {}))
    await act(async () => { await result.current.rerank({ base: 1, bonus: 0, equity: 0, fit: 0 }) })
    expect(result.current.error).toBe('Re-rank failed.')
    expect(result.current.leadError).toBeNull()
  })
})

describe('useJobSearch Edit draft', () => {
  it('never makes a draft: one gone from Gmail is said, and the job shows it has none', async () => {
    const inDrafts = job({ email_draft_id: 'r-1', email_drafted_at: '2026-10-17T00:00:00Z' })
    mock.get.mockResolvedValue(search({ leads: [inDrafts] }))
    mock.lead.mockResolvedValue(inDrafts)
    const { result } = await opened('l1')

    const now = job()
    mock.email.mockRejectedValueOnce(new ApiError("That draft isn't in your Gmail drafts any more.", 409, {
      detail: { code: 'email_draft_missing', message: "That draft isn't in your Gmail drafts any more.", lead: now },
    }))
    let draft: string | null = 'unset'
    await act(async () => { draft = await result.current.draftEmail('l1', true) })
    expect(draft).toBeNull()
    expect(mock.email).toHaveBeenCalledTimes(1)
    expect(mock.email).toHaveBeenCalledWith('s1', 'l1', true)
    expect(result.current.emailDraftGone).toBe(true)
    expect(result.current.leadError).toBeNull()
    expect(result.current.lead?.email_draft_id).toBeNull()
    expect(result.current.detail?.leads[0].email_draft_id).toBeNull()

    // Draft email, the person's own click, is what makes a new one.
    mock.email.mockResolvedValueOnce({ draft_id: 'r-2', to: '', subject: '', created: true, lead: job({ email_draft_id: 'r-2' }) })
    await act(async () => { draft = await result.current.draftEmail('l1') })
    expect(mock.email).toHaveBeenLastCalledWith('s1', 'l1', false)
    expect(draft).toBe('r-2')
    expect(result.current.emailDraftGone).toBe(false)
    expect(result.current.lead?.email_draft_id).toBe('r-2')
  })
})

describe('useJobSearch inside Tasks', () => {
  afterEach(() => vi.useRealTimers())

  it('loads and polls the search without loading the unused searches list', async () => {
    vi.useFakeTimers()
    mock.get.mockResolvedValueOnce(search({ status: 'discovering' })).mockResolvedValue(search())
    mock.status.mockResolvedValue({ id: 's1', status: 'done', fingerprint: 'f2', lead_count: 1 })
    const { result } = renderHook(() => useJobSearch('s1', null, { list: false }))
    await act(async () => {})
    expect(result.current.detail?.status).toBe('discovering')
    expect(mock.list).not.toHaveBeenCalled()
    await act(async () => { await vi.advanceTimersByTimeAsync(5_000) })
    expect(mock.status).toHaveBeenCalledTimes(1)
    expect(result.current.detail?.status).toBe('done')
    expect(mock.list).not.toHaveBeenCalled()
  })

  it('guards retained mutation callbacks while the owning task is deleting, then allows recovery', async () => {
    mock.get.mockResolvedValue(search())
    mock.lead.mockResolvedValue(job())
    mock.update.mockResolvedValue(job({ user_state: 'saved' }))
    const { result, rerender } = renderHook(
      ({ deleting }) => useJobSearch('s1', 'l1', { list: false, mutationsDisabled: deleting }),
      { initialProps: { deleting: false } },
    )
    await act(async () => {})
    const actions = result.current
    rerender({ deleting: true })
    await act(async () => {
      await actions.setLeadState('saved', 'l1')
      await actions.saveNotes('Notes to keep', 'l1')
      await actions.redraft()
      expect(await actions.draftEmail('l1')).toBeNull()
      expect(await actions.draftEmail('l1', true)).toBeNull()
      await actions.rerank({ base: 1, bonus: 0, equity: 0, fit: 0 })
    })
    expect(mock.update).not.toHaveBeenCalled()
    expect(mock.redraft).not.toHaveBeenCalled()
    expect(mock.email).not.toHaveBeenCalled()
    expect(mock.rerank).not.toHaveBeenCalled()
    rerender({ deleting: false })
    await act(async () => { await actions.setLeadState('saved', 'l1') })
    expect(mock.update).toHaveBeenCalledWith('s1', 'l1', { user_state: 'saved' })
  })
})
