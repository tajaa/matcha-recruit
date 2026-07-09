import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  AlertTriangle, BookOpen, CheckCircle2, ExternalLink, FileText, Loader2,
  Scale, ShieldCheck, Sparkles,
} from 'lucide-react'
import {
  getPilotHandbook, runComplianceScan,
  type AssembledHandbook, type AssembledSection, type ComplianceScanResult, type ComplianceGap,
  type CoverageEntry,
} from '../../../api/handbookPilot'
import { HelpHint } from '../../../components/ui/HelpHint'
import RequirementsPanel, { SEVERITY_STYLE } from './RequirementsPanel'

// ---------------------------------------------------------------------------
// HandbookViewer — the "living handbook". Assembles the session's drafts into a
// readable, cataloged document. Click a section/policy to see how it's grounded
// (which real jurisdiction requirements it cites) and, after a compliance scan,
// which required topics are still missing (the "why this isn't compliant" gaps).
// Purely additive to Handbook Pilot's Build mode — read-only, no editing here.
// ---------------------------------------------------------------------------

// Placeholder tokens the pilot leaves for the admin to resolve, e.g.
// [HR_CONTACT_EMAIL]. Wrap them in inline-code so prose styling makes them pop,
// but never touch markdown link syntax like [text](url).
function highlightPlaceholders(md: string): string {
  return (md || '').replace(/\[([A-Z0-9_]{2,})\](?!\()/g, '`[$1]`')
}

function statusDot(s: AssembledSection) {
  if (s.status === 'promoted') return <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
  const color = s.grounded ? 'bg-emerald-500' : 'bg-amber-500'
  return <span className={`h-2 w-2 rounded-full shrink-0 ${color}`} />
}

export default function HandbookViewer({ sessionId, refreshKey, onDraftRequirement }: {
  sessionId: string
  refreshKey: string | number
  onDraftRequirement: (req: CoverageEntry) => void
}) {
  const [handbook, setHandbook] = useState<AssembledHandbook | null>(null)
  const [loading, setLoading] = useState(true)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [scan, setScan] = useState<ComplianceScanResult | null>(null)
  const [scanning, setScanning] = useState(false)
  const [scanError, setScanError] = useState<string | null>(null)
  const sectionRefs = useRef<Record<string, HTMLDivElement | null>>({})

  const load = useCallback(async () => {
    try {
      const hb = await getPilotHandbook(sessionId)
      setHandbook(hb)
    } catch {
      setHandbook(null)
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  useEffect(() => { void load() }, [load, refreshKey])

  const allItems = useMemo(
    () => [...(handbook?.sections ?? []), ...(handbook?.policies ?? [])],
    [handbook],
  )
  const selected = allItems.find((s) => s.id === selectedId) ?? null

  const selectItem = (id: string) => {
    setSelectedId(id)
    sectionRefs.current[id]?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const scan_ = async () => {
    setScanning(true)
    setScanError(null)
    try {
      setScan(await runComplianceScan(sessionId))
    } catch (e) {
      setScanError(e instanceof Error ? e.message : 'Compliance scan failed — please try again.')
    } finally {
      setScanning(false)
    }
  }

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center border border-zinc-800 rounded-xl bg-zinc-950/40">
        <Loader2 className="h-6 w-6 animate-spin text-emerald-500" />
      </div>
    )
  }

  const summary = handbook?.summary
  const isEmpty = !handbook || (handbook.sections.length === 0 && handbook.policies.length === 0)

  return (
    <div className="flex-1 min-w-0 flex gap-4">
      {/* Section nav */}
      <aside className="w-56 shrink-0 flex flex-col border border-zinc-800 rounded-xl bg-zinc-950/40 overflow-hidden">
        <div className="px-3 py-2.5 border-b border-zinc-800 flex items-center gap-1.5">
          <BookOpen className="h-4 w-4 text-emerald-500" />
          <span className="text-sm font-semibold text-zinc-200">Contents</span>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-3">
          {isEmpty && (
            <p className="text-xs text-zinc-600 p-2">Nothing drafted yet. Switch to Build and ask the pilot to draft a section.</p>
          )}
          {handbook && handbook.sections.length > 0 && (
            <NavGroup label="Handbook sections" items={handbook.sections} selectedId={selectedId} onSelect={selectItem} />
          )}
          {handbook && handbook.policies.length > 0 && (
            <NavGroup label="Policies" items={handbook.policies} selectedId={selectedId} onSelect={selectItem} />
          )}
        </div>
      </aside>

      {/* Document */}
      <main className="flex-1 min-w-0 flex flex-col border border-zinc-800 rounded-xl bg-zinc-950/40 overflow-hidden">
        <div className="px-4 py-2.5 border-b border-zinc-800 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 flex-wrap text-[11px] text-zinc-500">
            {summary && (
              <>
                <Chip>{summary.section_count} sections</Chip>
                <Chip>{summary.policy_count} policies</Chip>
                <Chip className="text-emerald-400">{summary.grounded_sections} grounded</Chip>
                {summary.law_records > 0 && (
                  <>
                    <Chip className={summary.uncovered > 0 ? 'text-amber-400' : 'text-emerald-400'}>
                      {summary.covered}/{summary.law_records} requirements cited
                    </Chip>
                    <HelpHint text="Deterministic count: requirements whose id is cited by at least one draft, out of every requirement that applies to your work locations. The Requirements panel on the right lists them — and lets you draft the ones nothing cites yet." />
                  </>
                )}
              </>
            )}
          </div>
          <button
            onClick={() => void scan_()}
            disabled={scanning || isEmpty}
            className="shrink-0 text-xs px-2.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white inline-flex items-center gap-1.5"
            title="Grade the draft against the required topics for your jurisdictions"
          >
            {scanning ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ShieldCheck className="h-3.5 w-3.5" />}
            {scan ? 'Re-scan compliance' : 'Run compliance scan'}
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-6">
          {isEmpty ? (
            <div className="h-full flex flex-col items-center justify-center text-center text-zinc-600">
              <Sparkles className="h-8 w-8 text-zinc-700 mb-3" />
              <p className="text-sm">Your handbook appears here as the pilot drafts it.</p>
            </div>
          ) : (
            <div className="max-w-[70ch] mx-auto space-y-8">
              {handbook!.sections.map((s) => (
                <DocBlock key={s.id} item={s} selected={s.id === selectedId}
                  refCb={(el) => { sectionRefs.current[s.id] = el }} onSelect={() => setSelectedId(s.id)} />
              ))}
              {handbook!.policies.length > 0 && (
                <div className="pt-2 border-t border-zinc-800">
                  <div className="flex items-center gap-2 mb-4 text-xs uppercase tracking-wide text-zinc-500">
                    <FileText className="h-3.5 w-3.5" /> Standalone policies
                  </div>
                  <div className="space-y-8">
                    {handbook!.policies.map((s) => (
                      <DocBlock key={s.id} item={s} selected={s.id === selectedId}
                        refCb={(el) => { sectionRefs.current[s.id] = el }} onSelect={() => setSelectedId(s.id)} />
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </main>

      {/* Compliance detail */}
      <aside className="w-80 shrink-0 overflow-y-auto">
        <CompliancePanel
          sessionId={sessionId}
          refreshKey={refreshKey}
          selected={selected}
          handbook={handbook}
          scan={scan}
          scanError={scanError}
          onSelectClear={() => setSelectedId(null)}
          onDraftRequirement={onDraftRequirement}
          onViewSection={selectItem}
        />
      </aside>
    </div>
  )
}

// --------------------------------------------------------------------------- //

function Chip({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <span className={`px-2 py-0.5 rounded-md bg-zinc-800/60 border border-zinc-700/50 ${className}`}>{children}</span>
}

function NavGroup({ label, items, selectedId, onSelect }: {
  label: string; items: AssembledSection[]; selectedId: string | null; onSelect: (id: string) => void
}) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-zinc-600 px-2 mb-1">{label}</div>
      <div className="space-y-0.5">
        {items.map((s) => (
          <button
            key={s.id}
            onClick={() => onSelect(s.id)}
            className={`w-full text-left px-2 py-1.5 rounded-lg flex items-center gap-2 transition ${
              selectedId === s.id ? 'bg-emerald-500/10 border border-emerald-500/30' : 'hover:bg-zinc-800/60 border border-transparent'
            }`}
          >
            {statusDot(s)}
            <span className="text-[12px] text-zinc-300 truncate flex-1">{s.title}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

function DocBlock({ item, selected, refCb, onSelect }: {
  item: AssembledSection; selected: boolean; refCb: (el: HTMLDivElement | null) => void; onSelect: () => void
}) {
  const promotedHref = item.promoted_ref?.handbook_id
    ? `/app/handbook/${item.promoted_ref.handbook_id}`
    : item.promoted_ref?.policy_id ? '/app/policies' : null
  return (
    <div ref={refCb} onClick={onSelect}
      className={`scroll-mt-4 rounded-lg -mx-3 px-3 py-2 cursor-pointer transition ${
        selected ? 'bg-emerald-500/[0.04] ring-1 ring-emerald-500/20' : 'hover:bg-zinc-900/40'}`}>
      <div className="flex items-baseline justify-between gap-3 mb-1.5">
        <h2 className="text-lg font-semibold text-zinc-100">{item.title}</h2>
        <div className="flex items-center gap-2 shrink-0">
          {item.grounded && (
            <span className="inline-flex items-center gap-1 text-[10px] text-emerald-400" title="Grounded in real jurisdiction requirements">
              <Scale className="h-3 w-3" /> {item.law_citation_count}
            </span>
          )}
          {item.status === 'promoted' && promotedHref && (
            <a href={promotedHref} onClick={(e) => e.stopPropagation()}
              className="inline-flex items-center gap-1 text-[10px] text-emerald-400 hover:underline">
              Added <ExternalLink className="h-3 w-3" />
            </a>
          )}
          {item.status !== 'promoted' && (
            <span className="text-[10px] uppercase tracking-wide text-zinc-600">draft</span>
          )}
        </div>
      </div>
      <div className="prose prose-sm prose-invert prose-zinc max-w-none text-sm leading-relaxed text-zinc-300 prose-headings:text-zinc-100 prose-p:my-2 prose-code:text-emerald-300 prose-code:bg-emerald-500/10 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:before:content-[''] prose-code:after:content-['']">
        <Markdown remarkPlugins={[remarkGfm]}>{highlightPlaceholders(item.content)}</Markdown>
      </div>
    </div>
  )
}

// --------------------------------------------------------------------------- //
// Compliance panel — provenance for the selected section + session-level gaps.
// --------------------------------------------------------------------------- //

function CompliancePanel({
  sessionId, refreshKey, selected, handbook, scan, scanError,
  onSelectClear, onDraftRequirement, onViewSection,
}: {
  sessionId: string
  refreshKey: string | number
  selected: AssembledSection | null
  handbook: AssembledHandbook | null
  scan: ComplianceScanResult | null
  scanError: string | null
  onSelectClear: () => void
  onDraftRequirement: (req: CoverageEntry) => void
  onViewSection: (draftId: string) => void
}) {
  const matchedForSelected = useMemo(() => {
    if (!selected || !scan) return []
    const t = (selected.title || '').trim().toLowerCase()
    return scan.matched.filter((m) => (m.matched_section_title || '').trim().toLowerCase() === t)
  }, [selected, scan])

  return (
    <div className="flex flex-col gap-4">
      {/* Selected section provenance */}
      {selected ? (
        <div className="border border-zinc-800 rounded-xl bg-zinc-950/40">
          <div className="px-3 py-2.5 border-b border-zinc-800 flex items-center justify-between">
            <span className="text-sm font-semibold text-zinc-200 truncate">{selected.title}</span>
            <button onClick={onSelectClear} className="text-[11px] text-zinc-500 hover:text-zinc-300">Clear</button>
          </div>
          <div className="p-3 space-y-3">
            <div>
              <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-zinc-500 mb-2">
                <ShieldCheck className="h-3.5 w-3.5 text-emerald-500" /> How it's grounded
                <HelpHint text="Every enforceable clause traces to a real requirement your company is subject to, its industry baseline, or an existing policy it builds on." />
              </div>
              {selected.citations.length === 0 ? (
                <p className="text-[12px] text-amber-400/80">
                  No citations — this section isn't yet grounded in a jurisdiction requirement. Ask the pilot to ground it, or treat it as informational.
                </p>
              ) : (
                <div className="space-y-1.5">
                  {selected.citations.map((c) => (
                    <div key={c.cid} className={`rounded-lg border px-2.5 py-1.5 ${
                      c.source === 'law' ? 'border-emerald-500/25 bg-emerald-500/[0.05]'
                        : c.source === 'unknown' ? 'border-amber-500/25 bg-amber-500/[0.05]'
                        : 'border-zinc-800 bg-zinc-900/40'}`}>
                      <div className="flex items-center gap-1.5">
                        {c.source === 'law' && <Scale className="h-3 w-3 text-emerald-400 shrink-0" />}
                        <span className="text-[12px] text-zinc-200 truncate flex-1">{c.ref}</span>
                      </div>
                      {c.summary && <p className="text-[11px] text-zinc-500 mt-0.5 line-clamp-2">{c.summary}</p>}
                      <span className="text-[10px] uppercase tracking-wide text-zinc-600">{c.source_label}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
            {matchedForSelected.length > 0 && (
              <div>
                <div className="text-[11px] uppercase tracking-wide text-emerald-500/80 mb-1.5">Confirmed covered</div>
                <ul className="space-y-1">
                  {matchedForSelected.map((m, i) => (
                    <li key={i} className="text-[12px] text-zinc-300 flex items-start gap-1.5">
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 mt-0.5 shrink-0" />
                      <span>{m.requirement_title} <span className="text-zinc-600">· {m.state}</span></span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="border border-zinc-800 rounded-xl bg-zinc-950/40 px-3 py-3">
          <p className="text-[12px] text-zinc-500">
            Click a section to see how it's grounded — the real jurisdiction requirements it cites.
          </p>
        </div>
      )}

      {/* Session-level compliance */}
      <div className="border border-zinc-800 rounded-xl bg-zinc-950/40">
        <div className="px-3 py-2.5 border-b border-zinc-800 flex items-center gap-1.5">
          <ShieldCheck className="h-4 w-4 text-emerald-500" />
          <span className="text-sm font-semibold text-zinc-200">Compliance</span>
          <HelpHint text="The scan grades each required topic against the language you've actually drafted, and explains what good looks like for the ones it can't find." />
        </div>
        <div className="p-3 space-y-3">
          <RequirementsPanel
            sessionId={sessionId}
            refreshKey={refreshKey}
            handbook={handbook}
            scan={scan}
            onDraft={onDraftRequirement}
            onViewSection={onViewSection}
            compact
          />

          {scanError && <p className="text-[12px] text-amber-400">⚠ {scanError}</p>}

          {!scan && (
            <p className="text-[11px] text-zinc-600">
              Run a compliance scan to grade the draft against each required topic and see what's missing.
            </p>
          )}

          {scan && (
            <div className="space-y-2">
              <div className="flex items-center gap-1.5 text-[11px]">
                {(['critical', 'important', 'recommended'] as const).map((sev) => (
                  scan.counts[sev] > 0 && (
                    <span key={sev} className={`px-1.5 py-0.5 rounded border ${SEVERITY_STYLE[sev]}`}>
                      {scan.counts[sev]} {sev}
                    </span>
                  )
                ))}
                {scan.gaps.length === 0 && (
                  <span className="inline-flex items-center gap-1 text-emerald-400">
                    <CheckCircle2 className="h-3.5 w-3.5" /> No gaps found
                  </span>
                )}
              </div>
              {scan.gaps.length > 0 && (
                <div className="space-y-1.5">
                  <div className="text-[11px] uppercase tracking-wide text-zinc-500">Needs attention</div>
                  {scan.gaps.map((g, i) => <GapCard key={i} gap={g} />)}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function GapCard({ gap }: { gap: ComplianceGap }) {
  const [open, setOpen] = useState(false)
  return (
    <button onClick={() => setOpen((o) => !o)}
      className="w-full text-left rounded-lg border border-zinc-800 bg-zinc-900/40 px-2.5 py-2 hover:border-zinc-700">
      <div className="flex items-start gap-1.5">
        <AlertTriangle className={`h-3.5 w-3.5 mt-0.5 shrink-0 ${
          gap.severity === 'critical' ? 'text-red-400' : gap.severity === 'important' ? 'text-amber-400' : 'text-sky-400'}`} />
        <span className="text-[12px] text-zinc-200 flex-1">{gap.requirement_title}</span>
        <span className={`text-[9px] uppercase px-1 py-0.5 rounded border shrink-0 ${SEVERITY_STYLE[gap.severity] ?? SEVERITY_STYLE.recommended}`}>
          {gap.severity}
        </span>
      </div>
      <div className="text-[10px] text-zinc-600 mt-0.5 pl-5">{gap.state}{gap.citation ? ` · ${gap.citation}` : ''}</div>
      {open && gap.what_good_looks_like && (
        <p className="text-[11px] text-zinc-400 mt-1.5 pl-5 leading-relaxed">{gap.what_good_looks_like}</p>
      )}
    </button>
  )
}
