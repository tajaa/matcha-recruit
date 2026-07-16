import { useState, useMemo, useEffect } from 'react'
import { Lock } from 'lucide-react'
import { Select } from '../ui'
import { LABEL } from '../ui/typography'
import { UpgradeUpsellCard } from '../UpgradeUpsellCard'
import { EmployeesTooltip } from './EmployeesTooltip'
import {
  useComplianceRequirements,
  useKnownAuthorities,
  normalizeCategoryKey,
  jurisdictionSectionId,
  requirementAuthority,
} from '../../hooks/compliance/useComplianceRequirements'
import type { ComplianceRequirement } from '../../types/compliance'
import { CATEGORY_LABELS } from '../../types/compliance'
import type { CategoryGroup } from '../../generated/complianceCategories'
import { JURISDICTION_LEVEL_LABELS, RATE_TYPE_LABELS } from '../../api/compliance'
import type { FacilityAttributes } from '../../types/compliance'
import type { ComplianceCheckMessage } from '../../hooks/compliance/useComplianceCheck'

// The group filter is derived from the requirements this tenant actually has —
// never from a static list of every group the product supports. A dental office
// was being offered "Oncology", "Behavioral Health" and "Life Sciences" lenses
// because this used to be a hardcoded array: a menu of the codebase, not of the
// business. Picking one showed an empty page, or (worse) another industry's
// obligations, on a page whose entire job is "what am I responsible for".

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
  /** A catalog requirement (jurisdiction_requirement_id + title) to focus —
   *  cited by the regulatory-ask sources. Expands its category, scrolls it into
   *  view, and highlights it. The title is the fallback when the row isn't in
   *  this location's list. */
  targetReq?: { id: string; title?: string | null } | null
  onTargetConsumed?: () => void
}

const GROUP_BY_STORAGE_KEY = 'compliance_req_groupby'
type GroupBy = 'topic' | 'jurisdiction'

export function ComplianceRequirementsTab({ requirements, loading, onPin, checkMessages, readOnly, previewCategoryLimit, targetReq, onTargetConsumed }: Props) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [groupFilter, setGroupFilter] = useState<'all' | CategoryGroup>('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [highlightId, setHighlightId] = useState<string | null>(null)
  const [groupBy, setGroupBy] = useState<GroupBy>(
    () => (localStorage.getItem(GROUP_BY_STORAGE_KEY) as GroupBy) || 'topic',
  )

  function changeGroupBy(next: GroupBy) {
    setGroupBy(next)
    localStorage.setItem(GROUP_BY_STORAGE_KEY, next)
  }

  // From the UNFILTERED set, so searching can't shrink the trusted set and
  // strand a row under a section name that just disappeared.
  const knownAuthorities = useKnownAuthorities(requirements)

  // Focus a requirement cited by the "Ask" sources: expand its category, scroll
  // to it, highlight it briefly.
  useEffect(() => {
    if (!targetReq) return
    const match = requirements.find((r) => r.jurisdiction_requirement_id === targetReq.id)
    if (!match) {
      // The location's requirements may still be in flight (clicking a source
      // with no location selected picks one, THEN fetches). Consuming the target
      // here would drop it before the data it needs ever arrives.
      if (loading || requirements.length === 0) return
      // A real miss: the "Ask" cites the shared catalog, which can hold a row
      // this location never materialized. Search by title so the click still
      // lands somewhere, instead of doing nothing at all.
      setSearchQuery(targetReq.title ?? '')
      setGroupFilter('all')
      onTargetConsumed?.()
      return
    }
    setSearchQuery('')
    setGroupFilter('all')
    // Expand under BOTH lenses' keys — the row is reachable from either, and
    // this stays correct if the user toggles the view after the jump.
    const cat = normalizeCategoryKey(match.category || 'other')
    const authority = requirementAuthority(match, knownAuthorities)
    const jurKey = `${jurisdictionSectionId(authority.level, authority.name)}::${cat}`
    setExpanded((prev) => new Set(prev).add(cat).add(jurKey))
    setHighlightId(match.id)
    const t = setTimeout(() => {
      document.querySelector(`[data-req-id="${match.id}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }, 60)
    const clear = setTimeout(() => setHighlightId(null), 4000)
    onTargetConsumed?.()
    return () => { clearTimeout(t); clearTimeout(clear) }
  }, [targetReq, requirements, loading, knownAuthorities, onTargetConsumed])

  const filteredRequirements = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return requirements
    return requirements.filter((r) => {
      const catLabel = (r.category && CATEGORY_LABELS[r.category]) || ''
      return (
        r.title?.toLowerCase().includes(q) ||
        r.description?.toLowerCase().includes(q) ||
        r.current_value?.toLowerCase().includes(q) ||
        // Match what the row DISPLAYS as its authority, not just the free text
        // behind it — searching "Los Angeles" should find the city's ordinances.
        requirementAuthority(r, knownAuthorities).name.toLowerCase().includes(q) ||
        r.jurisdiction_name?.toLowerCase().includes(q) ||
        r.category?.toLowerCase().includes(q) ||
        catLabel.toLowerCase().includes(q)
      )
    })
  }, [requirements, searchQuery, knownAuthorities])

  const { sectionedCategories, jurisdictionSections } = useComplianceRequirements(filteredRequirements, knownAuthorities)

  // Sections present in the UNFILTERED set — so the options don't churn as the
  // user types in the search box.
  const { sectionedCategories: allSections } = useComplianceRequirements(requirements)

  // Keyed on the INDUSTRY TAG, not on BEHAVIORAL_HEALTH_CATEGORIES. That set
  // contains quality_reporting, hipaa_privacy, state_licensing and
  // corporate_integrity — generic healthcare categories, not behavioral-health
  // ones. A dental practice's three Medi-Cal rows (PAVE, TAR, encounter data)
  // are quality_reporting, so the category set matched them and offered a
  // Behavioral Health lens to a dentist. `healthcare:behavioral_health` is the
  // field that actually means "this row is behavioral health".
  const hasBehavioralHealth = useMemo(
    () => requirements.some((r) =>
      (r.applicable_industries ?? []).includes('healthcare:behavioral_health'),
    ),
    [requirements],
  )

  const groupOptions = useMemo(() => {
    const opts = [{ value: 'all', label: 'All Categories' }]
    for (const s of allSections) {
      opts.push({ value: s.id, label: s.label })
    }
    // Behavioral health is a cross-cutting lens (it pulls categories out of
    // several sections), so it isn't a section of its own — offer it only when
    // the tenant genuinely has such rows.
    if (hasBehavioralHealth && !allSections.some((s) => s.id === 'behavioral_health')) {
      opts.push({ value: 'behavioral_health', label: 'Behavioral Health' })
    }
    return opts
  }, [allSections, hasBehavioralHealth])

  // A group the tenant no longer has (data re-synced, or the last row of that
  // group was filtered out) must not leave the page stuck on an empty lens.
  const activeGroup: 'all' | CategoryGroup = groupOptions.some((o) => o.value === groupFilter)
    ? groupFilter
    : 'all'

  const filteredSections = useMemo(() => {
    if (activeGroup === 'all') return sectionedCategories
    if (activeGroup === 'behavioral_health') {
      // Cross-cutting lens: pull the behavioral-health rows out of whatever
      // section they sit in. Matched ONLY on the row's industry tag. A category
      // like quality_reporting or hipaa_privacy belongs to every healthcare
      // provider, so BEHAVIORAL_HEALTH_CATEGORIES cannot decide this — falling
      // back to it for untagged rows would re-admit the same bug it just fixed.
      const isBh = (r: ComplianceRequirement) =>
        (r.applicable_industries ?? []).includes('healthcare:behavioral_health')
      return sectionedCategories
        .map((s) => ({
          ...s,
          categories: s.categories
            .map(([cat, reqs]) => [cat, reqs.filter(isBh)] as [string, ComplianceRequirement[]])
            .filter(([, reqs]) => reqs.length > 0),
        }))
        .filter((s) => s.categories.length > 0)
    }
    return sectionedCategories.filter((s) => s.id === activeGroup)
  }, [sectionedCategories, activeGroup])

  // Emptiness is per-lens: the topic lens can be narrowed by the group filter,
  // the jurisdiction lens only by search.
  const sectionCount = groupBy === 'jurisdiction' ? jurisdictionSections.length : filteredSections.length

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

  // One category accordion row — the single renderer for every view (topic,
  // jurisdiction, lite preview). `keyPrefix` namespaces the expansion key: the
  // same category appears under several authorities in the jurisdiction lens,
  // and an unprefixed key would open all of them at once.
  const renderCategoryRow = (cat: string, reqs: ComplianceRequirement[], keyPrefix = '') => {
    const key = `${keyPrefix}${cat}`
    return (
    <div key={key} className="border-b border-white/[0.06] last:border-0">
      <button type="button" onClick={() => toggle(key)}
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
        <span className="text-xs text-zinc-600">{expanded.has(key) ? '−' : '+'}</span>
      </button>
      {expanded.has(key) && (
        <div className="divide-y divide-white/[0.04]">
          {reqs.length === 0 ? (
            <p className="px-4 py-4 text-xs text-zinc-600">
              {missingCoverage.has(cat)
                ? 'Coverage pending. Run a compliance check or admin refresh.'
                : 'No active requirements detected yet.'}
            </p>
          ) : (
            reqs.map((req) => {
              const authority = requirementAuthority(req, knownAuthorities)
              return (
              <div key={req.id} data-req-id={req.id}
                className={`px-4 py-3 transition-colors ${
                  highlightId === req.id
                    ? 'bg-emerald-500/[0.07] ring-1 ring-inset ring-emerald-500/40'
                    : 'hover:bg-white/[0.02]'
                }`}>
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-zinc-200">{req.title}</p>
                    <div className="flex flex-wrap items-center gap-2 mt-1">
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.04] text-zinc-400 border border-white/[0.08]">
                        {JURISDICTION_LEVEL_LABELS[authority.level] || authority.level}
                      </span>
                      <span className="text-[11px] text-zinc-500">{authority.name}</span>
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
                    {req.statute_citation && (
                      <span
                        className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-900/20 text-emerald-400 border border-emerald-800/40"
                        title={req.citation_verified_at ? `Verified ${new Date(req.citation_verified_at).toLocaleDateString()}` : undefined}>
                        {req.statute_citation}
                      </span>
                    )}
                    {req.jurisdictional_basis?.map((b) => (
                      <span
                        key={b.item_id}
                        className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.04] text-zinc-400 border border-white/[0.08]"
                        title={`This ${req.jurisdiction_level} requirement sits on top of the ${b.level} floor — it must meet or exceed ${b.citation}, which does not itself set this value.`}>
                        {b.level} floor: {b.citation}
                      </span>
                    ))}
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
              )
            })
          )}
        </div>
      )}
    </div>
    )
  }

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
        {groupBy === 'topic' && groupOptions.length > 2 && (
          <div className="w-48 shrink-0">
            <Select label="" options={groupOptions} value={activeGroup}
              onChange={(e) => setGroupFilter(e.target.value as 'all' | CategoryGroup)} />
          </div>
        )}
        {/* Same requirements, two questions: "what subject is this?" (topic) vs
            "who is imposing it?" (jurisdiction). */}
        <div className="flex shrink-0 rounded-lg border border-white/[0.08] bg-zinc-950 p-0.5">
          {([['topic', 'By topic'], ['jurisdiction', 'By jurisdiction']] as const).map(([value, label]) => (
            <button key={value} type="button" onClick={() => changeGroupBy(value)}
              aria-pressed={groupBy === value}
              className={`px-2.5 py-1.5 text-[11px] font-medium rounded-md transition-colors ${
                groupBy === value ? 'bg-white/[0.08] text-zinc-200' : 'text-zinc-500 hover:text-zinc-300'
              }`}>
              {label}
            </button>
          ))}
        </div>
        <span className="font-mono text-[11px] font-medium px-2 py-1 rounded-md bg-white/[0.04] text-zinc-400 border border-white/[0.08] shrink-0 tabular-nums">
          {searchQuery ? `${filteredRequirements.length} / ${requirements.length}` : requirements.length}
        </span>
      </div>

      {groupBy === 'topic' && activeGroup === 'behavioral_health' && (
        <div className="rounded-lg border border-violet-800/40 bg-violet-950/20 px-4 py-3">
          <p className="text-sm text-violet-300/90">
            <span className="font-medium">Behavioral Health Facility</span>
            {' — '}
            Showing requirements for mental health parity, substance use disorder confidentiality (42 CFR Part 2), facility licensing, seclusion &amp; restraint, and workforce credentialing.
          </p>
        </div>
      )}

      {sectionCount === 0 && searchQuery ? (
        <div className="border border-white/[0.06] bg-zinc-950 rounded-lg px-4 py-6 text-center">
          <p className="text-sm text-zinc-500">No requirements matching &ldquo;{searchQuery}&rdquo;</p>
          <button type="button" onClick={() => setSearchQuery('')}
            className="text-xs text-emerald-500 hover:text-emerald-400 mt-1 transition-colors">Clear search</button>
        </div>
      ) : sectionCount === 0 ? (
        <div className="border border-white/[0.06] bg-zinc-950 rounded-lg px-4 py-6 text-center">
          <p className="text-sm text-zinc-600">No requirements found. Run a compliance check to populate.</p>
        </div>
      ) : groupBy === 'jurisdiction' ? (
        <div className="overflow-hidden rounded-xl border border-white/[0.06] bg-zinc-950">
          {jurisdictionSections.map((section) => (
            <div key={section.id}>
              <div className="flex items-center gap-2 border-t border-white/[0.06] first:border-t-0 bg-white/[0.02] px-4 py-2">
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.04] text-zinc-400 border border-white/[0.08]">
                  {JURISDICTION_LEVEL_LABELS[section.level] || section.level}
                </span>
                <h3 className={LABEL}>
                  {section.label} <span className="normal-case text-zinc-600">({section.requirementCount})</span>
                </h3>
              </div>
              {section.categories.map(([cat, reqs]) => renderCategoryRow(cat, reqs, `${section.id}::`))}
            </div>
          ))}
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
              {section.categories.map(([cat, reqs]) => renderCategoryRow(cat, reqs))}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
