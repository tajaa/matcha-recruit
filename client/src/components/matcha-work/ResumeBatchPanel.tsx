import { useState, useMemo } from 'react'
import { Search, ChevronDown, ChevronUp, MapPin, Briefcase, AlertTriangle, CheckCircle2, Loader2 } from 'lucide-react'
import type { ResumeCandidate } from '../../types/matcha-work'

type SortKey = 'name' | 'experience_years' | 'current_title' | 'location'

interface ResumeBatchPanelProps {
  state: Record<string, unknown>
  threadId: string
  lightMode: boolean
  streaming: boolean
}

export default function ResumeBatchPanel({ state, lightMode, streaming }: ResumeBatchPanelProps) {
  const candidates = (state.candidates as ResumeCandidate[] | undefined) ?? []
  const totalCount = (state.total_count as number) ?? candidates.length
  const analyzedCount = (state.analyzed_count as number) ?? candidates.filter((c) => c.status === 'analyzed').length
  const batchTitle = (state.batch_title as string) ?? 'Resume Batch'

  const [search, setSearch] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('experience_years')
  const [sortAsc, setSortAsc] = useState(false)
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const filtered = useMemo(() => {
    const q = search.toLowerCase()
    let list = candidates.filter((c) => c.status === 'analyzed')
    if (q) {
      list = list.filter(
        (c) =>
          c.name?.toLowerCase().includes(q) ||
          c.current_title?.toLowerCase().includes(q) ||
          c.location?.toLowerCase().includes(q) ||
          c.skills?.some((s) => s.toLowerCase().includes(q))
      )
    }
    list.sort((a, b) => {
      let av: string | number = '', bv: string | number = ''
      if (sortKey === 'experience_years') {
        av = a.experience_years ?? 0
        bv = b.experience_years ?? 0
      } else {
        av = (a[sortKey] ?? '').toString().toLowerCase()
        bv = (b[sortKey] ?? '').toString().toLowerCase()
      }
      if (av < bv) return sortAsc ? -1 : 1
      if (av > bv) return sortAsc ? 1 : -1
      return 0
    })
    return list
  }, [candidates, search, sortKey, sortAsc])

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortAsc(!sortAsc)
    } else {
      setSortKey(key)
      setSortAsc(key === 'name')
    }
  }

  const lm = lightMode
  const th = {
    bg: lm ? 'bg-white' : 'bg-zinc-950',
    border: lm ? 'border-zinc-200' : 'border-zinc-800',
    text: lm ? 'text-zinc-900' : 'text-zinc-100',
    sub: lm ? 'text-zinc-500' : 'text-zinc-400',
    muted: lm ? 'text-zinc-400' : 'text-zinc-500',
    card: lm ? 'bg-zinc-50 border-zinc-200 hover:bg-zinc-100' : 'bg-zinc-900 border-zinc-800 hover:bg-zinc-800/80',
    input: lm ? 'bg-zinc-100 text-zinc-900 border-zinc-300 placeholder-zinc-400' : 'bg-zinc-900 text-white border-zinc-700 placeholder-zinc-500',
    tag: lm ? 'bg-zinc-200 text-zinc-600' : 'bg-zinc-800 text-zinc-300',
    strength: lm ? 'text-emerald-700' : 'text-emerald-400',
    flag: lm ? 'text-amber-600' : 'text-amber-400',
    sortBtn: lm ? 'text-zinc-400 hover:text-zinc-700' : 'text-zinc-500 hover:text-zinc-200',
    sortActive: lm ? 'text-emerald-600' : 'text-emerald-400',
  }

  if (candidates.length === 0 && !streaming) {
    return (
      <div className={`hidden md:flex md:w-1/2 items-center justify-center ${th.bg}`}>
        <p className={`text-sm ${th.muted}`}>
          No resumes yet — drag and drop files to start a batch.
        </p>
      </div>
    )
  }

  return (
    <div className={`hidden md:flex md:w-1/2 flex-col ${th.bg}`}>
      {/* Header */}
      <div className={`px-4 py-3 border-b ${th.border}`}>
        <h3 className={`text-sm font-semibold ${th.text}`}>{batchTitle}</h3>
        <p className={`text-xs ${th.muted} mt-0.5`}>
          {analyzedCount} of {totalCount} analyzed
          {streaming && <Loader2 size={10} className="inline ml-1.5 animate-spin" />}
        </p>
      </div>

      {/* Search + Sort */}
      <div className={`px-4 py-2 border-b ${th.border} flex items-center gap-2`}>
        <div className="relative flex-1">
          <Search size={12} className={`absolute left-2.5 top-1/2 -translate-y-1/2 ${th.muted}`} />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name, title, skills..."
            className={`w-full text-xs rounded pl-7 pr-2 py-1.5 border focus:outline-none focus:border-emerald-600 ${th.input}`}
          />
        </div>
        <div className="flex gap-1">
          {(['experience_years', 'name', 'location'] as SortKey[]).map((key) => {
            const labels: Record<SortKey, string> = { experience_years: 'Exp', name: 'Name', location: 'Loc', current_title: 'Title' }
            const active = sortKey === key
            return (
              <button
                key={key}
                onClick={() => handleSort(key)}
                className={`text-[10px] font-medium px-2 py-1 rounded transition-colors ${active ? th.sortActive : th.sortBtn}`}
              >
                {labels[key]}
                {active && (sortAsc ? <ChevronUp size={8} className="inline ml-0.5" /> : <ChevronDown size={8} className="inline ml-0.5" />)}
              </button>
            )
          })}
        </div>
      </div>

      {/* Candidate cards */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
        {filtered.map((c) => {
          const expanded = expandedId === c.id
          return (
            <div
              key={c.id}
              onClick={() => setExpandedId(expanded ? null : c.id)}
              className={`rounded-lg border p-3 cursor-pointer transition-colors ${th.card}`}
            >
              {/* Top row */}
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className={`text-sm font-semibold truncate ${th.text}`}>{c.name ?? c.filename}</p>
                  <p className={`text-xs ${th.sub} truncate`}>
                    {c.current_title ?? 'N/A'}
                    {c.experience_years != null && <span> &middot; {c.experience_years} yrs</span>}
                  </p>
                </div>
                {c.location && (
                  <span className={`flex items-center gap-1 text-[10px] shrink-0 ${th.muted}`}>
                    <MapPin size={10} />
                    {c.location}
                  </span>
                )}
              </div>

              {/* Summary */}
              {c.summary && (
                <p className={`text-xs mt-1.5 leading-relaxed ${th.sub}`}>{c.summary}</p>
              )}

              {/* Skills tags */}
              {c.skills && c.skills.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-2">
                  {(expanded ? c.skills : c.skills.slice(0, 5)).map((s, i) => (
                    <span key={i} className={`text-[10px] px-1.5 py-0.5 rounded ${th.tag}`}>{s}</span>
                  ))}
                  {!expanded && c.skills.length > 5 && (
                    <span className={`text-[10px] px-1.5 py-0.5 ${th.muted}`}>+{c.skills.length - 5}</span>
                  )}
                </div>
              )}

              {/* Expanded details */}
              {expanded && (
                <div className="mt-2 pt-2 border-t border-dashed space-y-1.5" style={{ borderColor: lm ? '#e4e4e7' : '#27272a' }}>
                  {c.education && (
                    <p className={`text-xs ${th.sub}`}>
                      <Briefcase size={10} className="inline mr-1" />
                      {c.education}
                    </p>
                  )}
                  {c.certifications && c.certifications.length > 0 && (
                    <p className={`text-xs ${th.sub}`}>
                      Certs: {c.certifications.join(', ')}
                    </p>
                  )}
                  {c.email && <p className={`text-xs ${th.muted}`}>{c.email}</p>}
                  {c.phone && <p className={`text-xs ${th.muted}`}>{c.phone}</p>}
                  {c.strengths && c.strengths.length > 0 && (
                    <div className="space-y-0.5">
                      {c.strengths.map((s, i) => (
                        <p key={i} className={`text-xs ${th.strength}`}>
                          <CheckCircle2 size={10} className="inline mr-1" />{s}
                        </p>
                      ))}
                    </div>
                  )}
                  {c.flags && c.flags.length > 0 && (
                    <div className="space-y-0.5">
                      {c.flags.map((f, i) => (
                        <p key={i} className={`text-xs ${th.flag}`}>
                          <AlertTriangle size={10} className="inline mr-1" />{f}
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}

        {/* Pending/error candidates */}
        {candidates.filter((c) => c.status !== 'analyzed').map((c) => (
          <div key={c.id} className={`rounded-lg border p-3 opacity-50 ${th.card}`}>
            <p className={`text-xs ${th.muted}`}>
              {c.status === 'pending' ? <Loader2 size={10} className="inline mr-1 animate-spin" /> : <AlertTriangle size={10} className="inline mr-1" />}
              {c.filename} — {c.status === 'pending' ? 'processing...' : 'extraction failed'}
            </p>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className={`px-4 py-2 border-t ${th.border}`}>
        <p className={`text-[10px] ${th.muted}`}>
          {filtered.length} candidate{filtered.length !== 1 ? 's' : ''}
          {search && ` matching "${search}"`}
          {' '}&middot; sorted by {sortKey === 'experience_years' ? 'experience' : sortKey}
        </p>
      </div>
    </div>
  )
}
