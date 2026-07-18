import { useState, useMemo } from 'react'
import { Select } from '../ui'
import { LABEL } from '../ui/typography'
import { useComplianceRequirements, useKnownAuthorities, requirementAuthority } from '../../hooks/compliance/useComplianceRequirements'
import type { ComplianceRequirement } from '../../types/compliance'
import { CATEGORY_LABELS } from '../../types/compliance'
import type { CategoryGroup } from '../../generated/complianceCategories'
import { JURISDICTION_LEVEL_LABELS } from '../../api/compliance/compliance'
import { CategoryRow } from './ComplianceRequirementsTab/CategoryRow'
import { LitePreview } from './ComplianceRequirementsTab/LitePreview'
import { useTargetReqFocus } from './ComplianceRequirementsTab/useTargetReqFocus'
import { GROUP_BY_STORAGE_KEY } from './ComplianceRequirementsTab/constants'
import type { CategoryRowShared, GroupBy, Props } from './ComplianceRequirementsTab/types'

// The group filter is derived from the requirements this tenant actually has —
// never from a static list of every group the product supports. A dental office
// was being offered "Oncology", "Behavioral Health" and "Life Sciences" lenses
// because this used to be a hardcoded array: a menu of the codebase, not of the
// business. Picking one showed an empty page, or (worse) another industry's
// obligations, on a page whose entire job is "what am I responsible for".

export function ComplianceRequirementsTab({ requirements, loading, onPin, checkMessages, readOnly, previewCategoryLimit, targetReq, onTargetConsumed }: Props) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [groupFilter, setGroupFilter] = useState<'all' | CategoryGroup>('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [highlightId, setHighlightId] = useState<string | null>(null)
  const [groupBy, setGroupBy] = useState<GroupBy>(() =>
    // Validate rather than cast: an unrecognized stored value is neither lens,
    // which hides the topic filter and leaves both toggle buttons unpressed
    // while the body still renders topic.
    localStorage.getItem(GROUP_BY_STORAGE_KEY) === 'jurisdiction' ? 'jurisdiction' : 'topic',
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
  useTargetReqFocus({
    targetReq,
    requirements,
    loading,
    knownAuthorities,
    onTargetConsumed,
    setSearchQuery,
    setGroupFilter,
    setExpanded,
    setHighlightId,
  })

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
  const { sectionedCategories: allSections } = useComplianceRequirements(requirements, knownAuthorities)

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

  // Props shared by every place that renders a category accordion row.
  const rowShared: CategoryRowShared = {
    expanded,
    toggle,
    missingCoverage,
    knownAuthorities,
    highlightId,
    readOnly,
    onPin,
  }

  if (loading) return <p className="text-sm text-zinc-500">Loading requirements...</p>

  // Lite preview: first N categories sharp, the rest blurred under one CTA.
  if (previewCategoryLimit != null) {
    return (
      <LitePreview
        filteredSections={filteredSections}
        previewCategoryLimit={previewCategoryLimit}
        totalRequirements={requirements.length}
        {...rowShared}
      />
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
            className="w-full bg-zinc-900/40 border border-white/[0.08] rounded-lg pl-9 pr-8 py-2.5 text-sm text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition-colors"
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
        <div className="flex shrink-0 rounded-lg border border-white/[0.08] bg-zinc-900/40 p-0.5">
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

      {/* The server serves only requirements tied to a verified statute. Say so:
          a short list with no explanation reads as missing data, when it is in
          fact the opposite — everything here is something we can prove. */}
      <p className="text-[11px] text-zinc-500">
        Every requirement here is tied to a verified statute citation.
      </p>

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
        <div className="border border-white/[0.06] bg-zinc-900/40 rounded-lg px-4 py-6 text-center">
          <p className="text-sm text-zinc-500">No requirements matching &ldquo;{searchQuery}&rdquo;</p>
          <button type="button" onClick={() => setSearchQuery('')}
            className="text-xs text-emerald-500 hover:text-emerald-400 mt-1 transition-colors">Clear search</button>
        </div>
      ) : sectionCount === 0 ? (
        <div className="border border-white/[0.06] bg-zinc-900/40 rounded-lg px-4 py-6 text-center">
          <p className="text-sm text-zinc-600">No requirements found. Run a compliance check to populate.</p>
        </div>
      ) : groupBy === 'jurisdiction' ? (
        <div className="overflow-hidden rounded-xl border border-white/[0.06] bg-zinc-900/40">
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
              {section.categories.map(([cat, reqs]) => (
                <CategoryRow key={cat} cat={cat} reqs={reqs} keyPrefix={`${section.id}::`} {...rowShared} />
              ))}
            </div>
          ))}
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-white/[0.06] bg-zinc-900/40">
          {filteredSections.map((section) => (
            <div key={section.id}>
              <div className="border-t border-white/[0.06] first:border-t-0 bg-white/[0.02] px-4 py-2">
                <h3 className={LABEL}>
                  {section.label} <span className="normal-case text-zinc-600">({section.requirementCount})</span>
                </h3>
              </div>
              {section.categories.map(([cat, reqs]) => (
                <CategoryRow key={cat} cat={cat} reqs={reqs} {...rowShared} />
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
