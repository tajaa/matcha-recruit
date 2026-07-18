import { useCallback, useEffect, useRef, useState } from 'react'
import { api, authStreamHeaders } from '../../../../api/client'
import { extractCitation } from '../utils'
import type { PendingItem, ReviewGroup, ApproveResult, UncodifiedItem } from '../types'
import type { FitGatedRow } from '../../../../api/admin/adminOnboarding'
import { fromGated, fromUncodified } from './helpers'

export function usePipeline({
  initialSection, initialUncodifiedItems,
}: {
  initialSection?: string | null
  initialUncodifiedItems?: UncodifiedItem[]
}) {
  const [fitRefresh, setFitRefresh] = useState(0)
  // Coverage requests — one date-sorted list, category gaps + industry-specialty to-dos merged server-side
  const [pending, setPending] = useState<PendingItem[]>([])
  const [loadingRequests, setLoadingRequests] = useState(false)
  const [openIds, setOpenIds] = useState<Set<string>>(new Set())
  const [selected, setSelected] = useState<Record<string, Set<string>>>({})
  const [runningId, setRunningId] = useState<string | null>(null)
  const [runMessages, setRunMessages] = useState<string[]>([])

  // Review (staged research awaiting approval)
  const [reviewGroups, setReviewGroups] = useState<ReviewGroup[]>([])
  const [loadingReview, setLoadingReview] = useState(false)
  const [justStaged, setJustStaged] = useState(false)
  const [reviewResult, setReviewResult] = useState<string | null>(null)
  const [approveResults, setApproveResults] = useState<ApproveResult[]>([])

  // Codify modal — walks uncodified approved rows one after another.
  const [codifyRow, setCodifyRow] = useState<ApproveResult | null>(null)
  const [codifyForm, setCodifyForm] = useState({ citation: '', heading: '', source_url: '' })
  const [codifyBusy, setCodifyBusy] = useState(false)
  const [codifyError, setCodifyError] = useState<string | null>(null)

  const queueRef = useRef<HTMLDivElement>(null)
  const reviewRef = useRef<HTMLDivElement>(null)

  const fetchRequests = async () => {
    setLoadingRequests(true)
    try {
      const res = await api.get<{ items: PendingItem[] }>('/admin/pending-research')
      setPending(res.items)
    } catch { setPending([]) }
    finally { setLoadingRequests(false) }
  }

  const fetchReview = async () => {
    setLoadingReview(true)
    try {
      const r = await api.get<{ groups: ReviewGroup[] }>('/admin/research-review')
      setReviewGroups(r.groups)
    } catch { setReviewGroups([]) }
    finally { setLoadingReview(false) }
  }

  useEffect(() => { fetchRequests(); fetchReview() }, [])

  // Jump to the right section when arriving via a Command Center action.
  useEffect(() => {
    if (initialSection === 'review') reviewRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    else if (initialSection === 'queue') queueRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [initialSection])

  // Seed the codify chain from the Command Center's worklist (rows already
  // live from a past approve) and jump straight into the modal.
  useEffect(() => {
    if (!initialUncodifiedItems || initialUncodifiedItems.length === 0) return
    const results = initialUncodifiedItems.map(fromUncodified)
    setApproveResults(results)
    setReviewResult(null)
    openCodify(results[0])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialUncodifiedItems])

  async function dismissRequest(id: string) {
    await api.post(`/admin/jurisdiction-requests/${id}/dismiss`, {})
    setPending((prev) => prev.filter((p) => !(p.type === 'category' && p.id === id)))
  }

  function toggleSelectCategory(rowId: string, catId: string) {
    setSelected((prev) => {
      const next = { ...prev }
      const set = new Set(next[rowId] ?? [])
      if (set.has(catId)) set.delete(catId)
      else set.add(catId)
      next[rowId] = set
      return next
    })
  }

  function toggleOpen(id: string) {
    setOpenIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function runResearch(rowId: string, item: PendingItem, categoryKeys: string[] | null) {
    setRunningId(rowId); setRunMessages([])
    const body = item.type === 'category'
      ? { item_type: 'category', request_id: item.id, city: item.city, state: item.state, county: item.county, categories: categoryKeys }
      : { item_type: 'vertical', company_id: item.company_id, categories: categoryKeys }
    const base = import.meta.env.VITE_API_URL || '/api'
    authStreamHeaders().then((headers) => fetch(`${base}/admin/pending-research/run`, {
      method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    })).then(async (res) => {
      const reader = res.body?.getReader()
      const decoder = new TextDecoder()
      if (!reader) { setRunningId(null); return }
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        for (const line of decoder.decode(value).split('\n')) {
          if (line.startsWith(': ')) continue
          if (!line.startsWith('data: ')) continue
          const data = line.slice(6)
          if (data === '[DONE]') {
            setRunningId(null)
            setSelected((prev) => { const next = { ...prev }; delete next[rowId]; return next })
            fetchRequests()
            // Pull the freshly-staged drafts and scroll to Review — otherwise
            // the results "vanish" (they're staged, not live) with no signal.
            setReviewResult(null)
            setJustStaged(true)
            fetchReview().then(() => reviewRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
            return
          }
          try {
            const ev = JSON.parse(data)
            if (ev.type === 'error') { setRunMessages((p) => [...p, `Error: ${ev.message}`]); setRunningId(null); return }
            if (ev.message) setRunMessages((p) => [...p, ev.message])
          } catch {}
        }
      }
      setRunningId(null)
    }).catch(() => setRunningId(null))
  }

  async function approveReview(ids: string[], group: ReviewGroup) {
    const res = await api.post<{ activated: number; published: number; codified: number; uncodified: number; results?: ApproveResult[] }>(
      '/admin/research-review/approve',
      { ids, request_ids: group.request_ids, company_ids: group.company_ids },
    )
    const activated = res?.activated ?? ids.length
    const codified = res?.codified ?? 0
    const uncodified = res?.uncodified ?? Math.max(activated - codified, 0)
    setReviewResult(
      `Approved ${activated} · codified ${codified}` +
      (uncodified > 0 ? ` · ${uncodified} live, awaiting a statute match` : ''),
    )
    setApproveResults(res?.results ?? [])
    setJustStaged(false)
    fetchReview(); fetchRequests()
  }

  function openCodify(row: ApproveResult) {
    setCodifyError(null)
    setCodifyForm({
      citation: extractCitation(row.current_value, row.description, row.title),
      heading: row.title || '',
      source_url: row.source_url || '',
    })
    setCodifyRow(row)
  }

  function nextUncodified(afterId: string): ApproveResult | null {
    const rest = approveResults.filter((r) => !r.codified && r.id !== afterId)
    return rest[0] ?? null
  }

  async function submitCodify() {
    if (!codifyRow || !codifyForm.citation.trim()) return
    setCodifyBusy(true); setCodifyError(null)
    try {
      const res = await api.post<{ codified: boolean; statute_citation: string | null; citation_url: string | null }>(
        `/admin/requirements/${codifyRow.id}/codify`,
        { citation: codifyForm.citation.trim(), heading: codifyForm.heading.trim() || null, source_url: codifyForm.source_url.trim() || null },
      )
      const doneId = codifyRow.id
      setApproveResults((prev) => prev.map((r) => r.id === doneId ? {
        ...r, codified: res.codified, statute_citation: res.statute_citation, citation_url: res.citation_url,
      } : r))
      // A codified row leaves `gated` and joins `visible` — re-measure so the
      // focused company's tiles move as you work, which is the whole feedback
      // loop this lens exists to give.
      if (res.codified) setFitRefresh((n) => n + 1)
      const next = nextUncodified(doneId)
      if (next) openCodify(next)
      else setCodifyRow(null)
    } catch (e) {
      setCodifyError(e instanceof Error ? e.message : 'Codify failed')
    } finally {
      setCodifyBusy(false)
    }
  }

  async function rejectReview(ids: string[], group: ReviewGroup) {
    await api.post('/admin/research-review/reject', { ids, request_ids: group.request_ids })
    fetchReview(); fetchRequests()
  }

  /** Hand this company's withheld rows to the codify chain that already lives
   *  here — the same outcome-panel + modal walk the post-approve flow uses. No
   *  navigation: the whole reason the company lens belongs on this tab. */
  const codifyGated = useCallback((rows: FitGatedRow[]) => {
    if (!rows.length) return
    const results = rows.map(fromGated)
    setApproveResults(results)
    setReviewResult(`${results.length} withheld row${results.length === 1 ? '' : 's'} for this company — codify to release them.`)
    openCodify(results[0])
  }, [])

  return {
    fitRefresh,
    pending, loadingRequests, openIds, selected, runningId, runMessages,
    reviewGroups, loadingReview, justStaged, reviewResult, approveResults,
    codifyRow, setCodifyRow, codifyForm, setCodifyForm, codifyBusy, codifyError,
    queueRef, reviewRef,
    fetchRequests, fetchReview,
    dismissRequest, toggleSelectCategory, toggleOpen, runResearch,
    approveReview, openCodify, nextUncodified, submitCodify, rejectReview,
    codifyGated,
  }
}
