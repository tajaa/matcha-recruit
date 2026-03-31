import { useState, useMemo, useRef, useEffect } from 'react'
import { Search, Star, MapPin, ChevronDown, ChevronUp, Loader2, CheckCircle2, AlertTriangle, Video } from 'lucide-react'
import type { MWProject, RecruitingData } from '../../types/matcha-work'
import { toggleProjectShortlist, updateProjectPosting, getProjectDetail } from '../../api/matchaWork'

type Tab = 'posting' | 'candidates' | 'interviews' | 'shortlist'
type SortKey = 'name' | 'experience_years' | 'location'

interface RecruitingPipelineProps {
  project: MWProject
  projectId: string
  onUpdate: (project: MWProject) => void
  streaming?: boolean
}

const c = {
  bg: '#1e1e1e', cardBg: '#252526', border: '#333', text: '#d4d4d4',
  heading: '#e8e8e8', muted: '#6a737d', accent: '#ce9178', hoverBg: '#2a2d2e',
  green: '#22c55e', amber: '#f59e0b',
}

export default function RecruitingPipeline({ project, projectId, onUpdate }: RecruitingPipelineProps) {
  const data = (project.project_data || {}) as RecruitingData
  const posting = data.posting || {}
  const candidates = data.candidates || []
  const shortlistIds = new Set(data.shortlist_ids || [])

  const [tab, setTab] = useState<Tab>('posting')
  const [search, setSearch] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('experience_years')
  const [sortAsc, setSortAsc] = useState(false)
  const [saving, setSaving] = useState(false)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const saveTimer = useRef<ReturnType<typeof setTimeout>>(null)

  // Local posting fields — controlled inputs that sync from server
  const [localPosting, setLocalPosting] = useState<Record<string, string>>({})

  // Sync when project data changes (e.g., after AI populates fields)
  useEffect(() => {
    const p = ((project.project_data || {}) as RecruitingData).posting || {}
    setLocalPosting((prev) => {
      const next: Record<string, string> = {}
      for (const key of ['title', 'location', 'employment_type', 'compensation', 'description', 'requirements']) {
        // Server value wins if local is empty or server changed
        next[key] = (p as Record<string, string>)[key] || prev[key] || ''
      }
      return next
    })
  }, [project.project_data])

  function updateField(field: string, value: string) {
    setLocalPosting((prev) => ({ ...prev, [field]: value }))
    if (saveTimer.current) clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(async () => {
      setSaving(true)
      try {
        await updateProjectPosting(projectId, { ...posting, [field]: value })
        const updated = await getProjectDetail(projectId)
        onUpdate(updated)
      } catch {}
      setSaving(false)
    }, 1000)
  }

  async function finalizePosting() {
    setSaving(true)
    try {
      await updateProjectPosting(projectId, { ...posting, finalized: true })
      const updated = await getProjectDetail(projectId)
      onUpdate(updated)
    } catch {}
    setSaving(false)
  }

  async function handleToggleShortlist(candidateId: string) {
    try {
      const updated = await toggleProjectShortlist(projectId, candidateId) as unknown as MWProject
      onUpdate(updated)
    } catch {}
  }

  // Filtered/sorted candidates
  const filteredCandidates = useMemo(() => {
    const q = search.toLowerCase()
    let list = [...candidates]
    if (tab === 'shortlist') list = list.filter((c) => shortlistIds.has(c.id))
    if (tab === 'interviews') list = list.filter((c) => c.status === 'interview_sent' || c.status === 'interview_completed' || c.status === 'interview_in_progress')
    if (q) {
      list = list.filter((c) =>
        c.name?.toLowerCase().includes(q) ||
        c.current_title?.toLowerCase().includes(q) ||
        c.location?.toLowerCase().includes(q) ||
        c.skills?.some((s) => s.toLowerCase().includes(q))
      )
    }
    list.sort((a, b) => {
      let av: string | number = '', bv: string | number = ''
      if (sortKey === 'experience_years') { av = a.experience_years ?? 0; bv = b.experience_years ?? 0 }
      else { av = (a[sortKey] ?? '').toString().toLowerCase(); bv = (b[sortKey] ?? '').toString().toLowerCase() }
      if (av < bv) return sortAsc ? -1 : 1
      if (av > bv) return sortAsc ? 1 : -1
      return 0
    })
    return list
  }, [candidates, search, sortKey, sortAsc, tab, shortlistIds])

  const tabs: { key: Tab; label: string; count?: number }[] = [
    { key: 'posting', label: 'Posting' },
    { key: 'candidates', label: 'Candidates', count: candidates.length },
    { key: 'shortlist', label: 'Shortlist', count: shortlistIds.size },
    { key: 'interviews', label: 'Interviews', count: candidates.filter((c) => c.interview_id).length },
  ]

  const isFinalized = !!(posting as Record<string, unknown>).finalized

  return (
    <div className="flex flex-col w-full" style={{ background: c.bg }}>
      {/* Tabs */}
      <div className="flex items-center gap-0.5 px-3 py-2 overflow-x-auto" style={{ borderBottom: `1px solid ${c.border}` }}>
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className="px-3 py-1.5 text-xs font-medium rounded transition-colors whitespace-nowrap"
            style={{
              color: tab === t.key ? c.heading : c.muted,
              background: tab === t.key ? c.hoverBg : 'transparent',
            }}
          >
            {t.label}
            {t.count != null && t.count > 0 && (
              <span className="ml-1 text-[9px] px-1 py-0.5 rounded-full" style={{ background: c.border, color: c.muted }}>
                {t.count}
              </span>
            )}
          </button>
        ))}
        {saving && <Loader2 size={10} className="ml-auto animate-spin" style={{ color: c.muted }} />}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto">
        {/* ── Posting Tab ── */}
        {tab === 'posting' && (
          <div className="p-4 space-y-3">
            {isFinalized && (
              <div className="flex items-center gap-2 px-3 py-2 rounded" style={{ background: '#22c55e20', border: `1px solid ${c.green}40` }}>
                <CheckCircle2 size={14} style={{ color: c.green }} />
                <span className="text-xs font-medium" style={{ color: c.green }}>Posting Finalized</span>
                <span className="text-[10px] ml-auto" style={{ color: c.muted }}>Drop resumes in the chat to add candidates</span>
              </div>
            )}
            {[
              { key: 'title', label: 'Job Title', type: 'input' },
              { key: 'location', label: 'Location', type: 'input' },
              { key: 'employment_type', label: 'Employment Type', type: 'input' },
              { key: 'compensation', label: 'Compensation', type: 'input' },
              { key: 'description', label: 'Description', type: 'textarea' },
              { key: 'requirements', label: 'Requirements', type: 'textarea' },
            ].map(({ key, label, type }) => (
              <div key={key}>
                <label className="text-[10px] font-medium mb-1 block" style={{ color: c.muted }}>{label}</label>
                {type === 'textarea' ? (
                  <textarea
                    value={localPosting[key] || ''}
                    onChange={(e) => updateField(key, e.target.value)}
                    rows={4}
                    className="w-full text-xs rounded border p-2 focus:outline-none resize-none"
                    style={{ background: '#1a1a1a', color: c.text, borderColor: c.border }}
                    placeholder={`Enter ${label.toLowerCase()}...`}
                  />
                ) : (
                  <input
                    value={localPosting[key] || ''}
                    onChange={(e) => updateField(key, e.target.value)}
                    className="w-full text-xs rounded border px-2 py-1.5 focus:outline-none"
                    style={{ background: '#1a1a1a', color: c.text, borderColor: c.border }}
                    placeholder={`Enter ${label.toLowerCase()}...`}
                  />
                )}
              </div>
            ))}
            {!isFinalized && (
              <button
                onClick={finalizePosting}
                disabled={saving || !localPosting.title}
                className="w-full py-2 text-xs font-medium rounded transition-colors disabled:opacity-40"
                style={{ background: c.green, color: '#fff' }}
              >
                Finalize Posting
              </button>
            )}
          </div>
        )}

        {/* ── Candidates / Shortlist / Interviews Tab ── */}
        {(tab === 'candidates' || tab === 'shortlist' || tab === 'interviews') && (
          <div>
            {/* Search + Sort */}
            <div className="px-3 py-2 flex items-center gap-2" style={{ borderBottom: `1px solid ${c.border}` }}>
              <div className="relative flex-1">
                <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2" style={{ color: c.muted }} />
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search name, title, skills..."
                  className="w-full text-xs rounded pl-7 pr-2 py-1.5 border focus:outline-none"
                  style={{ background: '#1a1a1a', color: c.text, borderColor: c.border }}
                />
              </div>
              {['experience_years', 'name', 'location'].map((key) => {
                const labels: Record<string, string> = { experience_years: 'Exp', name: 'Name', location: 'Loc' }
                const active = sortKey === key
                return (
                  <button
                    key={key}
                    onClick={() => { if (active) setSortAsc(!sortAsc); else { setSortKey(key as SortKey); setSortAsc(key === 'name') } }}
                    className="text-[10px] font-medium px-2 py-1 rounded"
                    style={{ color: active ? c.accent : c.muted }}
                  >
                    {labels[key]}
                    {active && (sortAsc ? <ChevronUp size={8} className="inline ml-0.5" /> : <ChevronDown size={8} className="inline ml-0.5" />)}
                  </button>
                )
              })}
            </div>

            {/* Candidate list */}
            <div className="p-3 space-y-2">
              {filteredCandidates.length === 0 && (
                <div className="text-center py-8" style={{ color: c.muted }}>
                  <p className="text-xs">
                    {tab === 'candidates' ? 'No candidates yet. Drop resumes in the chat.' :
                     tab === 'shortlist' ? 'No candidates shortlisted.' :
                     'No interviews yet.'}
                  </p>
                </div>
              )}
              {filteredCandidates.map((cand) => {
                const expanded = expandedId === cand.id
                const isShortlisted = shortlistIds.has(cand.id)
                return (
                  <div
                    key={cand.id}
                    onClick={() => setExpandedId(expanded ? null : cand.id)}
                    className="rounded-lg border p-3 cursor-pointer transition-colors"
                    style={{ background: c.cardBg, borderColor: c.border }}
                  >
                    <div className="flex items-start gap-2">
                      <button
                        onClick={(e) => { e.stopPropagation(); handleToggleShortlist(cand.id) }}
                        className="shrink-0 mt-0.5"
                        style={{ color: isShortlisted ? c.amber : c.muted }}
                      >
                        <Star size={14} fill={isShortlisted ? c.amber : 'none'} />
                      </button>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-medium truncate" style={{ color: c.heading }}>{cand.name ?? cand.filename}</p>
                          {cand.status === 'interview_sent' && (
                            <span className="text-[9px] px-1.5 py-0.5 rounded-full" style={{ background: '#3b82f620', color: '#60a5fa', border: '1px solid #3b82f640' }}>Interviewing</span>
                          )}
                          {cand.status === 'interview_completed' && (
                            <span className="text-[9px] px-1.5 py-0.5 rounded-full" style={{ background: '#22c55e20', color: c.green, border: `1px solid ${c.green}40` }}>
                              Done{cand.interview_score != null ? ` · ${cand.interview_score}%` : ''}
                            </span>
                          )}
                        </div>
                        <p className="text-xs" style={{ color: c.muted }}>
                          {cand.current_title ?? 'N/A'}
                          {cand.experience_years != null && ` · ${cand.experience_years} yrs`}
                        </p>
                      </div>
                      {cand.location && (
                        <span className="flex items-center gap-1 text-[10px] shrink-0" style={{ color: c.muted }}>
                          <MapPin size={10} />{cand.location}
                        </span>
                      )}
                    </div>

                    {cand.summary && (
                      <p className="text-xs mt-1.5 leading-relaxed" style={{ color: c.muted }}>{cand.summary}</p>
                    )}

                    {cand.skills && cand.skills.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        {(expanded ? cand.skills : cand.skills.slice(0, 5)).map((s, i) => (
                          <span key={i} className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: c.border, color: c.text }}>{s}</span>
                        ))}
                        {!expanded && cand.skills.length > 5 && (
                          <span className="text-[10px] px-1.5 py-0.5" style={{ color: c.muted }}>+{cand.skills.length - 5}</span>
                        )}
                      </div>
                    )}

                    {expanded && (
                      <div className="mt-2 pt-2 space-y-1" style={{ borderTop: `1px dashed ${c.border}` }}>
                        {cand.education && <p className="text-xs" style={{ color: c.muted }}>{cand.education}</p>}
                        {cand.email && <p className="text-xs" style={{ color: c.muted }}>{cand.email}</p>}
                        {cand.strengths?.map((s, i) => (
                          <p key={i} className="text-xs" style={{ color: c.green }}><CheckCircle2 size={10} className="inline mr-1" />{s}</p>
                        ))}
                        {cand.flags?.map((f, i) => (
                          <p key={i} className="text-xs" style={{ color: c.amber }}><AlertTriangle size={10} className="inline mr-1" />{f}</p>
                        ))}
                        {cand.interview_summary && (
                          <div className="mt-1 pt-1" style={{ borderTop: `1px dashed ${c.border}` }}>
                            <p className="text-[10px] font-medium" style={{ color: '#60a5fa' }}>
                              <Video size={10} className="inline mr-1" />Interview{cand.interview_score != null ? ` — ${cand.interview_score}%` : ''}
                            </p>
                            <p className="text-xs" style={{ color: c.muted }}>{cand.interview_summary}</p>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
