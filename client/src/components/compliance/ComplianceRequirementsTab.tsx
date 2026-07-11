import { useState, useMemo } from 'react'
import { Lock } from 'lucide-react'
import { Select } from '../ui'
import { LABEL } from '../ui/typography'
import { UpgradeUpsellCard } from '../UpgradeUpsellCard'
import { EmployeesTooltip } from './EmployeesTooltip'
import { useComplianceRequirements } from '../../hooks/compliance/useComplianceRequirements'
import type { ComplianceRequirement } from '../../types/compliance'
import { CATEGORY_LABELS } from '../../types/compliance'
import type { CategoryGroup } from '../../generated/complianceCategories'
import { BEHAVIORAL_HEALTH_CATEGORIES } from '../../generated/complianceCategories'
import { JURISDICTION_LEVEL_LABELS, RATE_TYPE_LABELS } from '../../api/compliance'
import type { FacilityAttributes } from '../../types/compliance'
import type { ComplianceCheckMessage } from '../../hooks/compliance/useComplianceCheck'

const GROUP_OPTIONS = [
  { value: 'all', label: 'All Categories' },
  { value: 'labor', label: 'Core Labor' },
  { value: 'supplementary', label: 'Supplementary' },
  { value: 'healthcare', label: 'Healthcare' },
  { value: 'behavioral_health', label: 'Behavioral Health' },
  { value: 'oncology', label: 'Oncology' },
  { value: 'medical_compliance', label: 'Medical Compliance' },
  { value: 'life_sciences', label: 'Life Sciences' },
]

type Props = {
  requirements: ComplianceRequirement[]
  loading: boolean
  onPin: (requirementId: string, isPinned: boolean) => void
  checkMessages: ComplianceCheckMessage[]
  facilityAttributes?: FacilityAttributes | null
  /** Read-only mode (compliance_lite taste) — hide Pin (the pin endpoint is
   *  Pro-gated and would 403). */
  readOnly?: boolean
  /** Lite preview: show only the first N categories fully; blur the rest behind
   *  an upgrade CTA. When set, the search/filter controls are hidden so the blur
   *  can't be bypassed. */
  previewCategoryLimit?: number
}

export function ComplianceRequirementsTab({ requirements, loading, onPin, checkMessages, readOnly, previewCategoryLimit }: Props) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [groupFilter, setGroupFilter] = useState<'all' | CategoryGroup>('all')
  const [searchQuery, setSearchQuery] = useState('')

  const filteredRequirements = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return requirements
    return requirements.filter((r) => {
      const catLabel = (r.category && CATEGORY_LABELS[r.category]) || ''
      return (
        r.title?.toLowerCase().includes(q) ||
        r.description?.toLowerCase().includes(q) ||
        r.current_value?.toLowerCase().includes(q) ||
        r.jurisdiction_name?.toLowerCase().includes(q) ||
        r.category?.toLowerCase().includes(q) ||
        catLabel.toLowerCase().includes(q)
      )
    })
  }, [requirements, searchQuery])

  const { sectionedCategories } = useComplianceRequirements(filteredRequirements)

  const filteredSections = useMemo(() => {
    if (groupFilter === 'all') return sectionedCategories
    if (groupFilter === 'behavioral_health') {
      // Cross-cutting filter: show categories from any section that are in BEHAVIORAL_HEALTH_CATEGORIES
      return sectionedCategories
        .map((s) => ({
          ...s,
          categories: s.categories.filter(([cat]) => BEHAVIORAL_HEALTH_CATEGORIES.has(cat)),
        }))
        .filter((s) => s.categories.length > 0)
    }
    return sectionedCategories.filter((s) => s.id === groupFilter)
  }, [sectionedCategories, groupFilter])

  // Detect missing coverage from check messages
  const missingCoverage = useMemo(() => {
    const cats = checkMessages.flatMap((m) => m.missing_categories ?? [])
    return new Set(cats.map((c) => c.trim().toLowerCase().replace(/[\s-]+/g, '_')))
  }, [checkMessages])

  function toggle(cat: string) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(cat)) next.delete(cat)
      else next.add(cat)
      return next
    })
  }

  // One category accordion row — shared by the normal and lite-preview renders.
  const renderCategoryRow = (cat: string, reqs: ComplianceRequirement[]) => (
    <div key={cat} className="border-b border-white/[0.06] last:border-0">
      <button type="button" onClick={() => toggle(cat)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-white/[0.02] transition-colors">
        <div className="flex items-center gap-3">
          <span className="text-xs font-medium text-zinc-200 uppercase tracking-wide">
            {CATEGORY_LABELS[cat] || cat}
          </span>
          <span className="text-[11px] text-zinc-600">{reqs.length} active</span>
          {missingCoverage.has(cat) && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-900/20 text-amber-400 border border-amber-800/40">Missing Coverage</span>
          )}
        </div>
        <span className="text-xs text-zinc-600">{expanded.has(cat) ? '−' : '+'}</span>
      </button>
      {expanded.has(cat) && (
        <div className="divide-y divide-white/[0.04]">
          {reqs.length === 0 ? (
            <p className="px-4 py-4 text-xs text-zinc-600">
              {missingCoverage.has(cat)
                ? 'Coverage pending. Run a compliance check or admin refresh.'
                : 'No active requirements detected yet.'}
            </p>
          ) : (
            reqs.map((req) => (
              <div key={req.id} className="px-4 py-3 hover:bg-white/[0.02] transition-colors">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-zinc-200">{req.title}</p>
                    <div className="flex flex-wrap items-center gap-2 mt-1">
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.04] text-zinc-400 border border-white/[0.08]">
                        {JURISDICTION_LEVEL_LABELS[req.jurisdiction_level] || req.jurisdiction_level}
                      </span>
                      <span className="text-[11px] text-zinc-500">{req.jurisdiction_name}</span>
                      {req.rate_type && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.04] text-zinc-500 border border-white/[0.08]">
                          {RATE_TYPE_LABELS[req.rate_type] || req.rate_type}
                        </span>
                      )}
                      {req.applicable_industries?.includes('healthcare') && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.04] text-zinc-400 border border-white/[0.08]">Medical</span>
                      )}
                      {(req.affected_employee_count ?? 0) > 0 && (
                        <EmployeesTooltip names={req.affected_employee_names} count={req.affected_employee_count!}>
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.04] text-zinc-400 border border-white/[0.08] cursor-default">
                            {req.affected_employee_count} employee{req.affected_employee_count !== 1 ? 's' : ''}
                          </span>
                        </EmployeesTooltip>
                      )}
                      {(req.min_wage_violation_count ?? 0) > 0 && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-900/20 text-red-400 border border-red-800/40">
                          {req.min_wage_violation_count} below threshold
                        </span>
                      )}
                    </div>
                  </div>
                  {req.current_value && (
                    <span className="text-sm font-mono text-zinc-200 bg-white/[0.06] border border-white/[0.08] px-2.5 py-1 rounded shrink-0">
                      {req.current_value}
                    </span>
                  )}
                </div>
                {req.description && (
                  <p className="text-xs text-zinc-500 mt-2 leading-relaxed">{req.description}</p>
                )}
                <div className="flex items-center justify-between mt-2">
                  <div className="flex items-center gap-3">
                    {req.effective_date && (
                      <span className="text-[11px] text-zinc-600">Eff. {new Date(req.effective_date).toLocaleDateString()}</span>
                    )}
                    {!readOnly && (
                      <button type="button" onClick={() => onPin(req.id, !req.is_pinned)}
                        className={`text-[11px] transition-colors ${req.is_pinned ? 'text-amber-400' : 'text-zinc-600 hover:text-amber-400'}`}>
                        {req.is_pinned ? 'Pinned' : 'Pin'}
                      </button>
                    )}
                  </div>
                  {req.source_url && (
                    <span className="flex items-center gap-1.5">
                      {req.source_url_status === 'dead' && (
                        <span
                          className="rounded border border-red-500/30 bg-red-500/15 px-1 py-px text-[10px] text-red-400"
                          title="This source link failed its last liveness check. The citation is kept so it can be re-verified once the authority fixes or moves the page.">
                          link broken
                        </span>
                      )}
                      <a href={req.source_url} target="_blank" rel="noopener noreferrer"
                        className="text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors">
                        Source &rarr;
                      </a>
                    </span>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )

  if (loading) return <p className="text-sm text-zinc-500">Loading requirements...</p>

  // Lite preview: first N categories sharp, the rest blurred under one CTA.
  if (previewCategoryLimit != null) {
    let budget = previewCategoryLimit
    const visibleSections: typeof filteredSections = []
    for (const s of filteredSections) {
      if (budget <= 0) break
      const take = s.categories.slice(0, budget)
      if (take.length > 0) visibleSections.push({ ...s, categories: take })
      budget -= take.length
    }
    // Everything not taken above, flattened, in order — the blurred remainder.
    let skip = previewCategoryLimit
    const hidden: { sectionLabel: string; cat: string; reqs: ComplianceRequirement[] }[] = []
    for (const s of filteredSections) {
      for (const [cat, reqs] of s.categories) {
        if (skip > 0) { skip -= 1; continue }
        hidden.push({ sectionLabel: s.label, cat, reqs })
      }
    }
    const hiddenReqCount = hidden.reduce((n, h) => n + h.reqs.length, 0)

    // Flatten the hidden categories into category-header + requirement rows so
    // the blurred wall shows the real VOLUME of requirements (not just collapsed
    // category names). Cap the DOM but keep enough to fill a tall, dense block.
    type BlurRow =
      | { kind: 'header'; key: string; cat: string; n: number }
      | { kind: 'req'; key: string; req: ComplianceRequirement }
    const blurRows: BlurRow[] = []
    for (const h of hidden) {
      blurRows.push({ kind: 'header', key: `h-${h.cat}`, cat: h.cat, n: h.reqs.length })
      for (const req of h.reqs) blurRows.push({ kind: 'req', key: req.id, req })
    }
    const cappedBlurRows = blurRows.slice(0, 80)

    return (
      <div className="space-y-4">
        <div className="overflow-hidden rounded-xl border border-white/[0.06] bg-zinc-950">
          {visibleSections.map((section) => (
            <div key={section.id}>
              <div className="border-t border-white/[0.06] first:border-t-0 bg-white/[0.02] px-4 py-2">
                <h3 className={LABEL}>{section.label}</h3>
              </div>
              {section.categories.map(([cat, reqs]) => renderCategoryRow(cat, reqs))}
            </div>
          ))}
        </div>

        {hidden.length > 0 && (
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Lock className="w-3.5 h-3.5 text-zinc-500" />
              <p className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wider">
                {hidden.length} more categories · {hiddenReqCount} requirements
              </p>
            </div>
            <div className="relative">
              {/* Dense blurred wall of real requirements — conveys the volume
                  behind the paywall. Tall but height-capped; fades out. */}
              <div className="border border-white/[0.06] bg-zinc-950 rounded-lg overflow-hidden max-h-[640px]">
                <div className="blur-[3px] select-none pointer-events-none" aria-hidden="true">
                  {cappedBlurRows.map((r) =>
                    r.kind === 'header' ? (
                      <div key={r.key} className="flex items-center gap-2 px-4 py-2 bg-white/[0.03] border-b border-white/[0.06]">
                        <span className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wide">{CATEGORY_LABELS[r.cat] || r.cat}</span>
                        <span className="text-[11px] text-zinc-600">{r.n} active</span>
                      </div>
                    ) : (
                      <div key={r.key} className="px-4 py-2.5 border-b border-white/[0.04]">
                        <div className="flex items-start justify-between gap-3">
                          <p className="text-sm text-zinc-200 truncate">{r.req.title}</p>
                          {r.req.current_value && (
                            <span className="text-[11px] font-mono text-zinc-200 bg-white/[0.06] border border-white/[0.08] px-2 py-0.5 rounded shrink-0">{r.req.current_value}</span>
                          )}
                        </div>
                        {r.req.description && (
                          <p className="text-[11px] text-zinc-500 mt-1 line-clamp-2">{r.req.description}</p>
                        )}
                      </div>
                    ),
                  )}
                </div>
              </div>
              {/* fade + centered unlock CTA */}
              <div className="absolute inset-x-0 bottom-0 h-48 bg-gradient-to-t from-zinc-950 via-zinc-950/85 to-transparent pointer-events-none" />
              <div className="absolute inset-0 flex items-center justify-center p-4">
                <div className="w-full max-w-md">
                  <UpgradeUpsellCard
                    source="compliance_lite:requirements"
                    title={`Unlock ${hiddenReqCount} more requirements`}
                    pitch={`You're seeing ${previewCategoryLimit} of ${hidden.length + previewCategoryLimit} categories. Upgrade to view all ${requirements.length} requirements for this location across every jurisdiction — with live monitoring and alerts.`}
                    bullets={[
                      'Every category for every location',
                      'Live re-research when laws change',
                      'Monitored alerts + action plans',
                      'Ask AI about any requirement',
                    ]}
                  />
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500 pointer-events-none" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search requirements..."
            className="w-full bg-zinc-950 border border-white/[0.08] rounded-lg pl-9 pr-8 py-2.5 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition-colors"
          />
          {searchQuery && (
            <button type="button" onClick={() => setSearchQuery('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300 transition-colors">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
        <div className="w-48 shrink-0">
          <Select label="" options={GROUP_OPTIONS} value={groupFilter}
            onChange={(e) => setGroupFilter(e.target.value as 'all' | CategoryGroup)} />
        </div>
        <span className="font-mono text-[11px] font-medium px-2 py-1 rounded-md bg-white/[0.04] text-zinc-400 border border-white/[0.08] shrink-0 tabular-nums">
          {searchQuery ? `${filteredRequirements.length} / ${requirements.length}` : requirements.length}
        </span>
      </div>

      {groupFilter === 'behavioral_health' && (
        <div className="rounded-lg border border-violet-800/40 bg-violet-950/20 px-4 py-3">
          <p className="text-sm text-violet-300/90">
            <span className="font-medium">Behavioral Health Facility</span>
            {' \u2014 '}
            Showing requirements for mental health parity, substance use disorder confidentiality (42 CFR Part 2), facility licensing, seclusion &amp; restraint, and workforce credentialing.
          </p>
        </div>
      )}

      {filteredSections.length === 0 && searchQuery ? (
        <div className="border border-white/[0.06] bg-zinc-950 rounded-lg px-4 py-6 text-center">
          <p className="text-sm text-zinc-500">No requirements matching &ldquo;{searchQuery}&rdquo;</p>
          <button type="button" onClick={() => setSearchQuery('')}
            className="text-xs text-emerald-500 hover:text-emerald-400 mt-1 transition-colors">Clear search</button>
        </div>
      ) : filteredSections.length === 0 ? (
        <div className="border border-white/[0.06] bg-zinc-950 rounded-lg px-4 py-6 text-center">
          <p className="text-sm text-zinc-600">No requirements found. Run a compliance check to populate.</p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-white/[0.06] bg-zinc-950">
          {filteredSections.map((section) => (
            <div key={section.id}>
              <div className="border-t border-white/[0.06] first:border-t-0 bg-white/[0.02] px-4 py-2">
                <h3 className={LABEL}>
                  {section.label} <span className="normal-case text-zinc-600">({section.requirementCount})</span>
                </h3>
              </div>
              {section.categories.map(([cat, reqs]) => (
                <div key={cat} className="border-b border-white/[0.06] last:border-0">
                  <button type="button" onClick={() => toggle(cat)}
                    className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-white/[0.02] transition-colors">
                    <div className="flex items-center gap-3">
                      <span className="text-xs font-medium text-zinc-200 uppercase tracking-wide">
                        {CATEGORY_LABELS[cat] || cat}
                      </span>
                      <span className="text-[11px] text-zinc-600">{reqs.length} active</span>
                      {missingCoverage.has(cat) && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-900/20 text-amber-400 border border-amber-800/40">Missing Coverage</span>
                      )}
                    </div>
                    <span className="text-xs text-zinc-600">{expanded.has(cat) ? '−' : '+'}</span>
                  </button>
                  {expanded.has(cat) && (
                    <div className="divide-y divide-white/[0.04]">
                      {reqs.length === 0 ? (
                        <p className="px-4 py-4 text-xs text-zinc-600">
                          {missingCoverage.has(cat)
                            ? 'Coverage pending. Run a compliance check or admin refresh.'
                            : 'No active requirements detected yet.'}
                        </p>
                      ) : (
                        reqs.map((req) => (
                          <div key={req.id} className="px-4 py-3 hover:bg-white/[0.02] transition-colors">
                            <div className="flex items-start justify-between gap-3">
                              <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium text-zinc-200">{req.title}</p>
                                <div className="flex flex-wrap items-center gap-2 mt-1">
                                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.04] text-zinc-400 border border-white/[0.08]">
                                    {JURISDICTION_LEVEL_LABELS[req.jurisdiction_level] || req.jurisdiction_level}
                                  </span>
                                  <span className="text-[11px] text-zinc-500">{req.jurisdiction_name}</span>
                                  {req.rate_type && (
                                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.04] text-zinc-500 border border-white/[0.08]">
                                      {RATE_TYPE_LABELS[req.rate_type] || req.rate_type}
                                    </span>
                                  )}
                                  {req.applicable_industries?.includes('healthcare') && (
                                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.04] text-zinc-400 border border-white/[0.08]">Medical</span>
                                  )}
                                  {(req.affected_employee_count ?? 0) > 0 && (
                                    <EmployeesTooltip names={req.affected_employee_names} count={req.affected_employee_count!}>
                                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.04] text-zinc-400 border border-white/[0.08] cursor-default">
                                        {req.affected_employee_count} employee{req.affected_employee_count !== 1 ? 's' : ''}
                                      </span>
                                    </EmployeesTooltip>
                                  )}
                                  {(req.min_wage_violation_count ?? 0) > 0 && (
                                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-900/20 text-red-400 border border-red-800/40">
                                      {req.min_wage_violation_count} below threshold
                                    </span>
                                  )}
                                </div>
                              </div>
                              {req.current_value && (
                                <span className="text-sm font-mono text-zinc-200 bg-white/[0.06] border border-white/[0.08] px-2.5 py-1 rounded shrink-0">
                                  {req.current_value}
                                </span>
                              )}
                            </div>
                            {req.description && (
                              <p className="text-xs text-zinc-500 mt-2 leading-relaxed">{req.description}</p>
                            )}
                            <div className="flex items-center justify-between mt-2">
                              <div className="flex items-center gap-3">
                                {req.effective_date && (
                                  <span className="text-[11px] text-zinc-600">Eff. {new Date(req.effective_date).toLocaleDateString()}</span>
                                )}
                                {!readOnly && (
                                  <button type="button" onClick={() => onPin(req.id, !req.is_pinned)}
                                    className={`text-[11px] transition-colors ${req.is_pinned ? 'text-amber-400' : 'text-zinc-600 hover:text-amber-400'}`}>
                                    {req.is_pinned ? 'Pinned' : 'Pin'}
                                  </button>
                                )}
                              </div>
                              {req.source_url && (
                                <span className="flex items-center gap-1.5">
                                  {req.source_url_status === 'dead' && (
                                    <span
                                      className="rounded border border-red-500/30 bg-red-500/15 px-1 py-px text-[10px] text-red-400"
                                      title="This source link failed its last liveness check. The citation is kept so it can be re-verified once the authority fixes or moves the page.">
                                      link broken
                                    </span>
                                  )}
                                  <a href={req.source_url} target="_blank" rel="noopener noreferrer"
                                    className="text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors">
                                    Source &rarr;
                                  </a>
                                </span>
                              )}
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
