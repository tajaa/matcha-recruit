import { BookOpen } from 'lucide-react'
import { SEVERITY_BADGE } from './constants'
import type { JurisdictionScope } from './types'

export function SeverityBadge({ severity }: { severity?: string | null }) {
  const key = (severity || '').toLowerCase()
  const cls = SEVERITY_BADGE[key]
  if (!cls) return null
  return (
    <span className={`ml-1.5 rounded border px-1 text-[9px] uppercase tracking-wide ${cls}`}
          title={`Severity: ${key}`}>
      {key}
    </span>
  )
}

// Sub-index jurisdiction narrowing — this tag reaches only named counties/cities.
export function ScopeChip({ scope }: { scope?: JurisdictionScope | null }) {
  if (!scope || !scope.names?.length) return null
  const plural = scope.level === 'city' ? 'cities' : scope.level === 'county' ? 'counties' : `${scope.level}s`
  return (
    <span className="ml-1.5 rounded border border-sky-500/30 bg-sky-500/15 px-1 text-[9px] text-sky-300"
          title={`Applies only to these ${plural}`}>
      {scope.level}: {scope.names.join(', ')}
    </span>
  )
}

// Reader-aware citation: opens the in-app statute drawer when body text exists,
// else links to the source, else plain text. Module-scope so it isn't a new
// component identity every parent render.
export function CitationLink({
  it, onOpen,
}: {
  it: { citation: string; item_id?: string | null; has_body?: boolean; source_url?: string | null }
  onOpen: (itemId: string) => void
}) {
  const cls = 'font-mono text-emerald-300/80 hover:text-emerald-200 hover:underline'
  if (it.has_body && it.item_id) {
    return (
      <button onClick={() => onOpen(it.item_id as string)} className={`${cls} inline-flex items-center gap-1`}
              title="Read the full regulation text">
        {it.citation}<BookOpen className="h-3 w-3 opacity-60" />
      </button>
    )
  }
  if (it.source_url) {
    return (
      <a href={it.source_url} target="_blank" rel="noreferrer" className={cls} title="Read the regulation (source)">
        {it.citation}
      </a>
    )
  }
  return <span className="font-mono text-emerald-300/80">{it.citation}</span>
}
