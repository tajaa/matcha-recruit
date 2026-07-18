import { Lock } from 'lucide-react'
import { LABEL } from '../../ui/typography'
import { UpgradeUpsellCard } from '../../shared/UpgradeUpsellCard'
import type { ComplianceRequirement } from '../../../types/compliance'
import { CATEGORY_LABELS } from '../../../types/compliance'
import type { CategorySection } from '../../../hooks/compliance/useComplianceRequirements'
import { CategoryRow } from './CategoryRow'
import type { CategoryRowShared } from './types'

type Props = CategoryRowShared & {
  filteredSections: CategorySection[]
  previewCategoryLimit: number
  totalRequirements: number
}

// Lite preview: first N categories sharp, the rest blurred under one CTA.
export function LitePreview({
  filteredSections,
  previewCategoryLimit,
  totalRequirements,
  ...rowProps
}: Props) {
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
      <div className="overflow-hidden rounded-xl border border-white/[0.06] bg-zinc-900/40">
        {visibleSections.map((section) => (
          <div key={section.id}>
            <div className="border-t border-white/[0.06] first:border-t-0 bg-white/[0.02] px-4 py-2">
              <h3 className={LABEL}>{section.label}</h3>
            </div>
            {section.categories.map(([cat, reqs]) => (
              <CategoryRow key={cat} cat={cat} reqs={reqs} {...rowProps} />
            ))}
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
            <div className="border border-white/[0.06] bg-zinc-900/40 rounded-lg overflow-hidden max-h-[640px]">
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
                  pitch={`You're seeing ${previewCategoryLimit} of ${hidden.length + previewCategoryLimit} categories. Upgrade to view all ${totalRequirements} requirements for this location across every jurisdiction — with live monitoring and alerts.`}
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
