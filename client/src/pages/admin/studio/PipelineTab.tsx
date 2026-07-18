import { useCallback, useEffect, useRef, useState } from 'react'
import { Building2, Check, ChevronDown, Circle, ExternalLink, Loader2, Sparkles, X } from 'lucide-react'
import { api, authStreamHeaders } from '../../../api/client'
import { Button, Modal, Input } from '../../../components/ui'
import { LABEL } from '../../../components/ui/typography'
import { extractCitation, coverageLink, libraryLink } from './utils'
import type { PendingItem, ReviewGroup, ApproveResult, UncodifiedItem } from './types'
import { CompanyPicker } from '../AdminOnboarding'
import StatutoryFitPanel from '../../../components/admin/onboarding/StatutoryFitPanel'
import type { FitGatedRow } from '../../../api/admin/adminOnboarding'

/** A withheld row from the fit map → the codify chain's shape.
 *  `catalog_id`, not `id`: codification acts on the catalog row, while `id` is
 *  the per-location projection. Seeding with the latter 404s on a row that
 *  plainly exists. */
function fromGated(g: FitGatedRow): ApproveResult {
  return {
    id: g.catalog_id, title: g.title ?? '(untitled)',
    // Carried, not nulled: openCodify pre-fills the citation box by scraping
    // these. Nulling them hands the admin an empty box on all 302 rows.
    description: g.description, current_value: g.current_value,
    source_url: g.source_url, source_name: g.source_name, regulation_key: g.regulation_key,
    codified: false, statute_citation: null, citation_url: null, citation_item_id: null,
    state: null, city: null,
  }
}

function fromUncodified(it: UncodifiedItem): ApproveResult {
  return {
    id: it.id, title: it.title, description: it.description, current_value: it.current_value,
    source_url: it.source_url, source_name: it.source_name, regulation_key: it.regulation_key,
    codified: false, statute_citation: null, citation_url: null, citation_item_id: null,
    state: it.state, city: it.city,
    blocked_companies: it.blocked_companies,
  }
}

// The DEMAND funnel, one stacked flow (no inner tabs): a company's coverage
// gap → research → staged review → approve (go live + publish) → codify.
// Section anchors let the Command Center jump straight to the right step via
// ?section=queue|review. `initialUncodifiedItems` seeds the codify chain
// directly from the Command Center's worklist (rows approved in a PAST
// session, not from a fresh approve just now) — reuses the exact same
// outcome-panel + modal UI built for the post-approve flow.
export default function PipelineTab({
  initialSection, initialUncodifiedItems, companyId, onCompanyChange,
}: {
  initialSection?: string | null
  initialUncodifiedItems?: UncodifiedItem[]
  /** Focus the tab on one tenant: the per-company job ("make THIS business
   *  whole") on the same funnel the queue below serves. Null = fleet view. */
  companyId?: string | null
  onCompanyChange?: (id: string | null) => void
}) {
  const [pickerOpen, setPickerOpen] = useState(false)
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

  return (
    <div className="space-y-6">
      {/* ── §0 Company focus ──
          The per-company job on the same funnel: pick a tenant, see what it
          still needs, and finish every step here — research, approve, codify —
          instead of the work being spread across Compliance Mgmt, Gap Analysis
          and this tab with no thread between them. */}
      <div className="flex items-center justify-between gap-3">
        <h2 className={LABEL}>{companyId ? 'Filling gaps for one company' : 'Fleet queue'}</h2>
        {companyId ? (
          <button type="button" onClick={() => onCompanyChange?.(null)}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/[0.08] px-2.5 h-8 text-xs text-emerald-300 hover:bg-emerald-500/[0.14]">
            <Building2 className="h-3.5 w-3.5" /> Focused — clear <X className="h-3 w-3" />
          </button>
        ) : (
          <Button variant="secondary" size="sm" onClick={() => setPickerOpen(true)}>
            <Building2 className="h-3.5 w-3.5" /> Focus a company
          </Button>
        )}
      </div>
      {pickerOpen && (
        <CompanyPicker onClose={() => setPickerOpen(false)}
                       onPick={(id) => { setPickerOpen(false); onCompanyChange?.(id) }} />
      )}
      {companyId && (
        <StatutoryFitPanel companyId={companyId} onCodifyGated={codifyGated} refreshKey={fitRefresh} />
      )}

      {/* ── §1 Queued coverage requests ── */}
      <div ref={queueRef}>
        <div className="flex items-center justify-between mb-2">
          <h2 className={LABEL}>Researching for tenants — newest first</h2>
          <Button variant="ghost" size="sm" onClick={fetchRequests}>Refresh</Button>
        </div>

        {runningId !== null && (
          <div className="mb-3 flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/[0.06] px-3 py-2.5">
            <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-emerald-400" />
            <p className="text-xs text-emerald-200">
              Researching… drafts appear below in Staged review when done.
              {runMessages.length > 0 && (
                <span className="ml-1.5 text-emerald-300/70">{runMessages[runMessages.length - 1]}</span>
              )}
            </p>
          </div>
        )}

        {loadingRequests ? (
          <p className="text-sm text-zinc-500">Loading...</p>
        ) : pending.length === 0 ? (
          <div className="border border-white/[0.06] rounded-lg px-4 py-8 text-center">
            <p className="text-sm text-zinc-600">Nothing outstanding — every onboarded tenant is fully covered.</p>
          </div>
        ) : (
          <div className="border border-white/[0.06] rounded-lg overflow-hidden">
            {pending.map((item) => {
              const rowId = item.type === 'category' ? `cat-${item.id}` : `vert-${item.company_id}-${item.label}`
              const open = openIds.has(rowId)
              const categoryNames = item.categories.map((c) => c.name).join(', ')
              return (
                <article key={rowId} className="border-b border-white/[0.06] last:border-b-0">
                  <button type="button" onClick={() => toggleOpen(rowId)}
                    className="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-white/[0.02]">
                    <ChevronDown className={`mt-1 h-4 w-4 shrink-0 text-zinc-600 transition-transform ${open ? 'rotate-0' : '-rotate-90'}`} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-3 font-mono text-[10px] uppercase tracking-wide text-zinc-500">
                        {item.created_at && <span className="tabular-nums">{new Date(item.created_at).toLocaleDateString()}</span>}
                        <span>{item.type === 'category' ? 'Category gap' : `Specialty · ${item.label}`}</span>
                      </div>
                      <h3 className="mt-1 truncate text-[15px] font-semibold text-zinc-100">
                        {item.type === 'category'
                          ? <>{item.city}, {item.state}{item.county && <span className="text-zinc-500 font-normal ml-1.5">({item.county} County)</span>}</>
                          : item.company_name}
                      </h3>
                      <p className="mt-0.5 truncate text-sm text-zinc-500">
                        {item.type === 'category' ? `${item.company_name} · ` : `${item.jurisdictions.join(', ')} · `}
                        {categoryNames}
                      </p>
                    </div>
                  </button>
                  {open && (
                    <div className="px-4 pb-4 pl-11">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-amber-400 text-[11px]">
                          {item.categories.length} to research
                        </span>
                        <span className="text-[10px] text-zinc-500">
                          · {item.type === 'category'
                            ? `${item.city}, ${item.state}`
                            : item.jurisdictions.join(', ')}
                        </span>
                      </div>

                      <div className="space-y-1.5">
                        {item.categories.map((c, i) => {
                          const catId = c.key ?? c.name
                          const checked = selected[rowId]?.has(catId) ?? false
                          return (
                            <label key={c.key ?? `${c.name}-${i}`}
                              className="flex cursor-pointer gap-2 rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
                              <input type="checkbox" checked={checked} disabled={runningId !== null}
                                onChange={() => toggleSelectCategory(rowId, catId)}
                                className="mt-0.5 h-3.5 w-3.5 shrink-0 accent-emerald-500" />
                              <div className="min-w-0 flex-1">
                                <div className="flex items-center justify-between gap-2">
                                  <span className="text-xs font-medium text-zinc-200">{c.name}</span>
                                  <span className="rounded border px-1.5 py-0.5 text-[10px] border-amber-500/30 bg-amber-500/10 text-amber-300 shrink-0">
                                    Needs research
                                  </span>
                                </div>
                                {c.description && (
                                  <p className="mt-1 text-[11px] text-zinc-400 leading-relaxed">{c.description}</p>
                                )}
                              </div>
                            </label>
                          )
                        })}
                      </div>

                      {runningId === rowId && runMessages.length > 0 && (
                        <div className="border border-zinc-800 rounded-lg px-3 py-2.5 mt-3 max-h-28 overflow-y-auto">
                          {runMessages.map((msg, i) => (
                            <p key={i} className="text-xs text-zinc-500 leading-5">{msg}</p>
                          ))}
                        </div>
                      )}

                      {(() => {
                        const selCount = selected[rowId]?.size ?? 0
                        const selKeys = [...(selected[rowId] ?? [])]
                        if (runningId === rowId) {
                          return (
                            <p className="mt-3 text-xs text-zinc-500">Researching… (staged for review)</p>
                          )
                        }
                        return (
                          <div className="mt-3 flex flex-wrap items-center gap-2">
                            <Button variant="secondary" size="sm"
                              disabled={selCount === 0 || runningId !== null}
                              onClick={() => runResearch(rowId, item, selKeys)}>
                              Research selected ({selCount})
                            </Button>
                            <Button variant="ghost" size="sm"
                              disabled={runningId !== null}
                              onClick={() => runResearch(rowId, item, null)}>
                              Research all
                            </Button>
                            {item.type === 'category' && (
                              <button type="button" onClick={() => dismissRequest(item.id)}
                                className="text-xs text-zinc-600 hover:text-zinc-300 px-2 py-1 transition-colors">Dismiss</button>
                            )}
                          </div>
                        )
                      })()}

                    </div>
                  )}
                </article>
              )
            })}
          </div>
        )}
      </div>

      {/* ── §2 Staged review + §3 Codify chain ── */}
      <div ref={reviewRef}>
        <div className="flex items-center justify-between mb-2">
          <h2 className={LABEL}>Staged research — approve to publish</h2>
          <Button variant="ghost" size="sm" onClick={fetchReview}>Refresh</Button>
        </div>

        {justStaged && (
          <div className="mb-3 flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/[0.06] px-3 py-2.5">
            <Sparkles className="h-3.5 w-3.5 shrink-0 text-amber-400" />
            <p className="text-xs text-amber-200">
              Research complete — staged below, not yet live. Review, then
              <span className="font-medium"> Approve</span> to publish to the tenant and codify.
            </p>
          </div>
        )}

        {reviewResult && (
          <div className="mb-3 flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/[0.06] px-3 py-2.5">
            <Check className="h-3.5 w-3.5 shrink-0 text-emerald-400" />
            <p className="text-xs text-emerald-200">{reviewResult}</p>
          </div>
        )}

        {approveResults.length > 0 && (() => {
          const remaining = approveResults.filter((r) => !r.codified)
          return (
          <div className="mb-4 rounded-lg border border-white/[0.08] bg-white/[0.02] overflow-hidden">
            <div className="flex items-center justify-between gap-2 border-b border-white/[0.06] px-3 py-2">
              <p className="font-mono text-[10px] uppercase tracking-wide text-zinc-500">
                {remaining.length === 0
                  ? `All ${approveResults.length} codified`
                  : `Codification outcome — ${approveResults.length - remaining.length}/${approveResults.length} codified`}
              </p>
              {remaining.length > 0 && (
                <Button variant="secondary" size="sm" onClick={() => openCodify(remaining[0])}>
                  Codify {remaining.length} →
                </Button>
              )}
            </div>
            <div className="divide-y divide-white/[0.04]">
              {approveResults.map((r) => (
                <div key={r.id} className="flex items-start gap-2.5 px-3 py-2.5">
                  {r.codified ? (
                    <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400" />
                  ) : (
                    <Circle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-400/70" />
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <p className="text-xs font-medium text-zinc-200">{r.title}</p>
                      {!r.codified && !!r.blocked_companies && (
                        // Which of these rows a customer is actually waiting on.
                        // Hidden once codified — the wait is over — and absent on
                        // fresh approves, where demand is unknown rather than zero.
                        <span
                          className="shrink-0 rounded-full border border-amber-800/40 bg-amber-900/20 px-1.5 py-0.5 font-mono text-[10px] text-amber-400"
                          title="Live tenants with this requirement projected but withheld from their tab">
                          blocks {r.blocked_companies}
                        </span>
                      )}
                    </div>
                    {r.codified ? (
                      <p className="mt-0.5 text-[11px] text-zinc-400">
                        Codified — {r.citation_url
                          ? <a href={r.citation_url} target="_blank" rel="noreferrer"
                              className="text-cyan-400 hover:text-cyan-300">{r.statute_citation || 'view statute'}</a>
                          : <span className="text-zinc-300">{r.statute_citation}</span>}
                        {(r.state || r.city) && <>
                          {' · '}
                          <a href={libraryLink(r.state, r.city)}
                            className="text-emerald-400 hover:text-emerald-300 inline-flex items-center gap-0.5">
                            View in Library <ExternalLink className="h-3 w-3" />
                          </a>
                        </>}
                      </p>
                    ) : (
                      <p className="mt-0.5 text-[11px] text-zinc-500">
                        Live, not yet codified.{' '}
                        <button type="button" onClick={() => openCodify(r)}
                          className="text-emerald-400 hover:text-emerald-300 font-medium">Codify now</button>
                        {' '}or open in{' '}
                        <a href={coverageLink(r.state, r.city)}
                          className="text-cyan-400 hover:text-cyan-300 inline-flex items-center gap-0.5">
                          Coverage <ExternalLink className="h-3 w-3" />
                        </a>.
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
          )
        })()}

        {loadingReview ? (
          <p className="text-sm text-zinc-500">Loading...</p>
        ) : reviewGroups.length === 0 ? (
          <div className="border border-white/[0.06] rounded-lg px-4 py-8 text-center">
            <p className="text-sm text-zinc-600">Nothing staged for review.</p>
          </div>
        ) : (
          <div className="space-y-4">
            {reviewGroups.map((group) => {
              const allIds = group.rows.map((r) => r.id)
              return (
                <div key={group.jurisdiction_id} className="border border-white/[0.06] rounded-lg overflow-hidden">
                  <div className="flex items-start justify-between gap-3 border-b border-white/[0.06] px-4 py-3">
                    <div className="min-w-0">
                      <h3 className="truncate text-[15px] font-semibold text-zinc-100">{group.label}</h3>
                      <p className="mt-0.5 flex items-center gap-2 font-mono text-[10px] uppercase tracking-wide text-zinc-500">
                        <span>{group.state} · {group.rows.length} staged</span>
                        <a href={coverageLink(group.state, group.city)}
                          className="inline-flex items-center gap-0.5 text-cyan-400/70 hover:text-cyan-300 normal-case tracking-normal">
                          Coverage <ExternalLink className="h-2.5 w-2.5" />
                        </a>
                      </p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <Button variant="secondary" size="sm" onClick={() => approveReview(allIds, group)}>
                        Approve all ({group.rows.length})
                      </Button>
                      <button type="button" onClick={() => rejectReview(allIds, group)}
                        className="text-xs text-zinc-600 hover:text-red-400 px-2 py-1 transition-colors">Reject all</button>
                    </div>
                  </div>

                  <div className="space-y-1.5 p-3">
                    {group.rows.map((row) => (
                      <div key={row.id} className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs font-medium text-zinc-200">{row.title}</span>
                          <span className={`rounded border px-1.5 py-0.5 text-[10px] shrink-0 ${
                            row.will_codify
                              ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
                              : 'border-zinc-600/40 bg-zinc-500/10 text-zinc-400'
                          }`} title={row.will_codify
                            ? 'A confirmed authority citation exists — approving will codify this automatically.'
                            : 'Research-cited, not yet registry-verified — approve, then Codify to confirm the statute citation.'}>
                            {row.will_codify ? 'Will codify' : 'Codify after approve'}
                          </span>
                        </div>
                        <p className="mt-0.5 text-[11px] text-zinc-500">
                          {row.category_name}
                          {row.source_name && (
                            <> · {row.source_url
                              ? <a href={row.source_url} target="_blank" rel="noreferrer" className="text-cyan-400/70 hover:text-cyan-300">{row.source_name}</a>
                              : <span className="text-zinc-400">{row.source_name}</span>}</>
                          )}
                        </p>
                        {row.description && (
                          <p className="mt-1 text-[11px] text-zinc-400 leading-relaxed">{row.description}</p>
                        )}
                        {row.current_value && (
                          <p className="mt-1 text-[11px] text-zinc-300">{row.current_value}</p>
                        )}
                        <div className="mt-2 flex items-center gap-3">
                          <button type="button" onClick={() => approveReview([row.id], group)}
                            className="text-xs text-emerald-400 hover:text-emerald-300 transition-colors">Approve</button>
                          <button type="button" onClick={() => rejectReview([row.id], group)}
                            className="text-xs text-zinc-600 hover:text-red-400 transition-colors">Reject</button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Codify modal — mint the authority citation for a live requirement, in
          place. Walks the approved rows one after another. */}
      <Modal open={codifyRow !== null} onClose={() => setCodifyRow(null)}
        title="Codify requirement" width="md">
        {codifyRow && (
          <div className="space-y-3">
            <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2.5">
              <p className="text-xs font-medium text-zinc-200">{codifyRow.title}</p>
              <p className="mt-0.5 font-mono text-[10px] text-zinc-500">
                {codifyRow.regulation_key || 'no key'} · {(codifyRow.state || '').toUpperCase()}{codifyRow.city ? `, ${codifyRow.city}` : ''}
              </p>
              <p className="mt-1 text-[11px] text-zinc-500">
                Confirm the statute citation for this requirement. It's stored as a
                verified authority citation — the same registry the Authority tab reads.
              </p>
            </div>

            <Input id="codify-citation" label="Statute citation" required
              value={codifyForm.citation}
              onChange={(e) => setCodifyForm({ ...codifyForm, citation: e.target.value })}
              placeholder="e.g. C.R.S. § 12-220-101" />
            <Input id="codify-heading" label="Heading (optional)"
              value={codifyForm.heading}
              onChange={(e) => setCodifyForm({ ...codifyForm, heading: e.target.value })}
              placeholder="short label for the statute" />
            <Input id="codify-source" label="Source URL (optional)"
              value={codifyForm.source_url}
              onChange={(e) => setCodifyForm({ ...codifyForm, source_url: e.target.value })}
              placeholder="https://…" />

            {codifyError && <p className="text-[11px] text-red-400">{codifyError}</p>}

            <div className="flex items-center justify-between gap-2 pt-1">
              <button type="button"
                onClick={() => { const n = nextUncodified(codifyRow.id); if (n) openCodify(n); else setCodifyRow(null) }}
                className="text-xs text-zinc-600 hover:text-zinc-300 transition-colors">Skip</button>
              <Button size="sm" disabled={codifyBusy || !codifyForm.citation.trim()} onClick={submitCodify}>
                {codifyBusy ? 'Codifying…' : 'Codify + next'}
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
