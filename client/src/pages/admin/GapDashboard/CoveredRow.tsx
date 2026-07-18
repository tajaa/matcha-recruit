import { useState } from 'react'
import { Loader2, CheckCircle2, ChevronRight, ExternalLink } from 'lucide-react'
import { adminOnboarding } from '../../../api/admin/adminOnboarding'
import type { GapRequirementDetail } from '../../../api/admin/adminOnboarding'
import { humanizeCategory, jurisdictionLabel } from '../../../components/admin/onboarding/GapCard'
import type { CoveredItem } from './types'

export default function CoveredRow({ companyId, item }: { companyId: string; item: CoveredItem }) {
  const [open, setOpen] = useState(false)
  const [detail, setDetail] = useState<GapRequirementDetail | null>(null)
  const [loading, setLoading] = useState(false)

  function toggle() {
    const next = !open
    setOpen(next)
    if (next && !detail && item.requirement_id) {
      setLoading(true)
      adminOnboarding.getRequirementDetail(companyId, item.requirement_id)
        .then(setDetail).catch(() => {}).finally(() => setLoading(false))
    }
  }

  return (
    <div className="border-b border-vsc-border last:border-0">
      <button onClick={toggle} className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-vsc-bg/40">
        <ChevronRight className={`w-3.5 h-3.5 text-zinc-600 transition-transform ${open ? 'rotate-90' : ''}`} />
        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
        <span className="text-xs text-zinc-200 truncate">{item.title || humanizeCategory(item.category_slug || '')}</span>
        <span className="text-[10px] text-zinc-500 ml-auto shrink-0">{jurisdictionLabel(item)}</span>
      </button>
      {open && (
        <div className="px-9 pb-3 text-[11px] text-zinc-400 space-y-1">
          {loading && <span className="inline-flex items-center gap-1.5"><Loader2 className="w-3 h-3 animate-spin" /> loading…</span>}
          {detail && (
            <>
              {detail.current_value && <div><span className="text-zinc-500">Value: </span><span className="text-zinc-200 font-mono">{detail.current_value}</span>{detail.rate_type ? ` (${detail.rate_type})` : ''}</div>}
              {detail.description && <div className="leading-relaxed">{detail.description}</div>}
              {Array.isArray(detail.implementation_steps) && detail.implementation_steps.length > 0 && (
                <div className="pt-0.5">
                  <div className="text-zinc-500 mb-1">How to comply:</div>
                  <ol className="list-decimal pl-4 space-y-1 text-zinc-300 marker:text-vsc-accent">
                    {detail.implementation_steps.map((s, i) => <li key={i} className="leading-relaxed">{s}</li>)}
                  </ol>
                </div>
              )}
              {detail.effective_date && <div><span className="text-zinc-500">Effective: </span>{detail.effective_date}</div>}
              {detail.requires_written_policy && <div className="text-amber-300">Requires a written policy (handbook).</div>}
              {detail.source_url && (
                <a href={detail.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-emerald-300 hover:underline">
                  <ExternalLink className="w-3 h-3" /> {detail.source_name || 'Source'}
                </a>
              )}
              {!detail.description && !detail.current_value && <div className="text-zinc-500 italic">No additional detail recorded.</div>}
            </>
          )}
        </div>
      )}
    </div>
  )
}
