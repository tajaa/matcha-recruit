import { useState, useMemo, useRef, useCallback } from 'react'
import { Search, Star, MapPin, ChevronDown, ChevronUp, Loader2, CheckCircle2, AlertTriangle, Video, Send, Square, CheckSquare, RefreshCw, GripVertical, Plus, Trash2, FileText } from 'lucide-react'
import type { MWProject, RecruitingData } from '../../types/matcha-work'
import { toggleProjectShortlist, getProjectDetail, addProjectSectionNew, updateProjectSectionNew, deleteProjectSectionNew, updateProjectPosting } from '../../api/matchaWork'
import SectionEditor from './SectionEditor'
import { sectionToHtml } from './markdownToHtml'

type Tab = 'posting' | 'candidates' | 'interviews' | 'shortlist'
type SortKey = 'name' | 'experience_years' | 'location'

interface RecruitingPipelineProps {
  project: MWProject
  projectId: string
  onUpdate: (project: MWProject) => void
  streaming?: boolean
  onSendInterviews?: (candidateIds: string[], positionTitle?: string) => Promise<void>
  onSyncInterviews?: () => Promise<void>
  onPromptChat?: (placeholders: PlaceholderInfo[]) => void
}

interface PlaceholderInfo {
  placeholder: string  // e.g. "[Number]"
  label: string        // e.g. "Number of locations"
}

/** Extract [bracketed] placeholders with surrounding context for friendly labels */
function extractPlaceholders(html: string): PlaceholderInfo[] {
  const text = html.replace(/<[^>]+>/g, '').replace(/\n/g, ' ')
  const results: PlaceholderInfo[] = []
  const seen = new Set<string>()
  const regex = /\[([^\]]+)\]/g
  let match
  while ((match = regex.exec(text)) !== null) {
    if (seen.has(match[0])) continue
    seen.add(match[0])
    // Grab surrounding words for context
    const before = text.slice(Math.max(0, match.index - 40), match.index).trim().split(/\s+/).slice(-4).join(' ')
    const after = text.slice(match.index + match[0].length, match.index + match[0].length + 40).trim().split(/\s+/).slice(0, 4).join(' ')
    const name = match[1]
    // Build a contextual label
    let label = name
    if (before || after) {
      label = `${before} ___${name}___ ${after}`.trim()
    }
    results.push({ placeholder: match[0], label })
  }
  return results
}

const c = {
  bg: '#1e1e1e', cardBg: '#252526', border: '#333', text: '#d4d4d4',
  heading: '#e8e8e8', muted: '#6a737d', accent: '#ce9178', hoverBg: '#2a2d2e',
  green: '#22c55e', amber: '#f59e0b',
}

export default function RecruitingPipeline({ project, projectId, onUpdate, onSendInterviews, onSyncInterviews, onPromptChat }: RecruitingPipelineProps) {
  const data = (project.project_data || {}) as RecruitingData
  const posting = data.posting || {}
  const candidates = data.candidates || []
  const shortlistIds = new Set(data.shortlist_ids || [])
  const sections = project.sections ?? []

  const [tab, setTab] = useState<Tab>('posting')
  const [search, setSearch] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('experience_years')
  const [sortAsc, setSortAsc] = useState(false)
  const [saving, setSaving] = useState(false)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [sendingInterviews, setSendingInterviews] = useState(false)
  const [positionInput, setPositionInput] = useState('')
  const [showPositionPrompt, setShowPositionPrompt] = useState(false)

  // Section title editing + save feedback
  const [sectionTitleEditing, setSectionTitleEditing] = useState<string | null>(null)
  const [sectionTitleDraft, setSectionTitleDraft] = useState('')
  const [showSaved, setShowSaved] = useState(false)
  const saveTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({})
  const savedTimer = useRef<ReturnType<typeof setTimeout>>(null)

  const isFinalized = !!(posting as Record<string, unknown>).finalized

  const placeholderCount = useMemo(() => {
    const all: string[] = []
    for (const s of sections) all.push(...extractPlaceholders(s.content))
    return all.length
  }, [sections])

  // ── Section CRUD ──

  async function refreshProject() {
    const updated = await getProjectDetail(projectId)
    onUpdate(updated)
  }

  function handleSectionContentUpdate(sectionId: string, html: string) {
    clearTimeout(saveTimers.current[sectionId])
    saveTimers.current[sectionId] = setTimeout(() => {
      flushSave(sectionId, html)
    }, 1000)
  }

  function flashSaved() {
    setShowSaved(true)
    if (savedTimer.current) clearTimeout(savedTimer.current)
    savedTimer.current = setTimeout(() => setShowSaved(false), 2000)
  }

  const flushSave = useCallback(async (sectionId: string, content: string) => {
    setSaving(true)
    try {
      await updateProjectSectionNew(projectId, sectionId, { content })
      await refreshProject()
      flashSaved()
    } catch {}
    setSaving(false)
  }, [projectId])

  async function saveSectionTitle(sectionId: string, newTitle: string) {
    setSaving(true)
    try {
      await updateProjectSectionNew(projectId, sectionId, { title: newTitle })
      await refreshProject()
      flashSaved()
    } catch {}
    setSaving(false)
    setSectionTitleEditing(null)
  }

  async function handleDeleteSection(sectionId: string) {
    try {
      await deleteProjectSectionNew(projectId, sectionId)
      await refreshProject()
    } catch {}
  }

  async function handleAddBlankSection() {
    try {
      await addProjectSectionNew(projectId, { content: '', title: 'New Section' })
      await refreshProject()
    } catch {}
  }

  async function finalizePosting() {
    // Check for unfilled [bracketed] placeholders in all sections
    const allPlaceholders: PlaceholderInfo[] = []
    for (const s of sections) {
      allPlaceholders.push(...extractPlaceholders(s.content))
    }
    if (allPlaceholders.length > 0 && onPromptChat) {
      onPromptChat(allPlaceholders)
      return
    }

    setSaving(true)
    try {
      await updateProjectPosting(projectId, { ...posting, finalized: true })
      await refreshProject()
    } catch {}
    setSaving(false)
  }

  // ── Candidate selection + interviews ──

  async function handleToggleShortlist(candidateId: string) {
    try {
      const updated = await toggleProjectShortlist(projectId, candidateId) as unknown as MWProject
      onUpdate(updated)
    } catch {}
  }

  const selectableIds = useMemo(() =>
    candidates.filter((c) => c.status === 'analyzed' && c.email).map((c) => c.id),
    [candidates]
  )

  const hasInterviews = candidates.some((c) => c.interview_id)

  function toggleSelect(id: string, e: React.MouseEvent) {
    e.stopPropagation()
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleSelectAll() {
    if (selectedIds.size >= selectableIds.length) setSelectedIds(new Set())
    else setSelectedIds(new Set(selectableIds))
  }

  async function handleSendInterviews() {
    if (!onSendInterviews || selectedIds.size === 0) return
    setSendingInterviews(true)
    try {
      await onSendInterviews(Array.from(selectedIds), positionInput.trim() || undefined)
      setSelectedIds(new Set())
      setShowPositionPrompt(false)
      setPositionInput('')
    } catch {
      // error handled by parent
    }
    setSendingInterviews(false)
  }

  // ── Filtered/sorted candidates ──

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
    { key: 'posting', label: 'Posting', count: sections.length },
    { key: 'candidates', label: 'Candidates', count: candidates.length },
    { key: 'shortlist', label: 'Shortlist', count: shortlistIds.size },
    { key: 'interviews', label: 'Interviews', count: candidates.filter((c) => c.interview_id).length },
  ]

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
        <div className="flex items-center gap-1.5 ml-auto">
          {saving && <Loader2 size={10} className="animate-spin" style={{ color: c.muted }} />}
          {!saving && showSaved && <span className="text-[10px] font-medium" style={{ color: c.green }}>Saved</span>}
          {hasInterviews && onSyncInterviews && (
            <button
              onClick={onSyncInterviews}
              title="Refresh interview statuses"
              className="p-1 rounded transition-colors"
              style={{ color: c.muted }}
            >
              <RefreshCw size={10} />
            </button>
          )}
          {tab === 'candidates' && selectableIds.length > 0 && onSendInterviews && (
            <button
              onClick={toggleSelectAll}
              className="text-[10px] font-medium px-2 py-1 rounded transition-colors"
              style={{ color: c.muted }}
            >
              {selectedIds.size >= selectableIds.length ? 'Clear' : 'Select All'}
            </button>
          )}
          {selectedIds.size > 0 && onSendInterviews && !showPositionPrompt && (
            <button
              onClick={() => setShowPositionPrompt(true)}
              disabled={sendingInterviews}
              className="flex items-center gap-1 text-[10px] font-medium px-2.5 py-1 rounded transition-colors disabled:opacity-40"
              style={{ background: c.green, color: '#fff' }}
            >
              <Video size={10} />
              Interview ({selectedIds.size})
            </button>
          )}
        </div>
      </div>
      {/* Position title prompt */}
      {showPositionPrompt && (
        <div className="flex items-center gap-2 px-3 py-2" style={{ borderBottom: `1px solid ${c.border}` }}>
          <input
            value={positionInput}
            onChange={(e) => setPositionInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleSendInterviews() }}
            placeholder="Position title (e.g. Senior Engineer)"
            autoFocus
            className="flex-1 text-xs rounded px-2.5 py-1.5 border focus:outline-none"
            style={{ background: '#1a1a1a', color: c.text, borderColor: c.border }}
          />
          <button
            onClick={handleSendInterviews}
            disabled={sendingInterviews}
            className="p-1.5 rounded transition-colors disabled:opacity-40"
            style={{ background: c.green, color: '#fff' }}
          >
            {sendingInterviews ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
          </button>
          <button
            onClick={() => { setShowPositionPrompt(false); setPositionInput('') }}
            className="text-[10px]"
            style={{ color: c.muted }}
          >
            Cancel
          </button>
        </div>
      )}

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto">
        {/* ── Posting Tab — Section-based editor ── */}
        {tab === 'posting' && (
          <div>
            {isFinalized && (
              <div className="flex items-center gap-2 px-3 py-2 mx-3 mt-3 rounded" style={{ background: '#22c55e20', border: `1px solid ${c.green}40` }}>
                <CheckCircle2 size={14} style={{ color: c.green }} />
                <span className="text-xs font-medium" style={{ color: c.green }}>Posting Finalized</span>
                <span className="text-[10px] ml-auto" style={{ color: c.muted }}>Drop resumes in the chat to add candidates</span>
              </div>
            )}

            {sections.length === 0 && (
              <div className="text-center py-12" style={{ color: c.muted }}>
                <FileText size={24} className="mx-auto mb-2 opacity-40" />
                <p className="text-xs">No sections yet.</p>
                <p className="text-xs mt-1">Use the chat to describe the role, then click <strong style={{ color: c.accent }}>"Add to Project"</strong> on any message.</p>
              </div>
            )}

            {sections.map((s) => (
              <div key={s.id} style={{ borderBottom: `1px solid ${c.border}` }}>
                {/* Section header */}
                <div className="flex items-center gap-1.5 px-4 py-1.5" style={{ background: c.cardBg }}>
                  <GripVertical size={12} className="shrink-0 cursor-grab" style={{ color: c.muted }} />
                  {sectionTitleEditing === s.id ? (
                    <input
                      value={sectionTitleDraft}
                      onChange={(e) => setSectionTitleDraft(e.target.value)}
                      onBlur={() => saveSectionTitle(s.id, sectionTitleDraft)}
                      onKeyDown={(e) => { if (e.key === 'Enter') saveSectionTitle(s.id, sectionTitleDraft) }}
                      autoFocus
                      className="flex-1 text-xs font-semibold rounded px-1.5 py-0.5 border focus:outline-none"
                      style={{ background: c.bg, color: c.heading, borderColor: '#555' }}
                    />
                  ) : (
                    <span
                      onClick={() => { setSectionTitleEditing(s.id); setSectionTitleDraft(s.title || '') }}
                      className="flex-1 text-xs font-semibold truncate cursor-pointer"
                      style={{ color: s.title ? c.heading : c.muted }}
                    >
                      {s.title || 'Untitled section'}
                    </span>
                  )}
                  <button
                    onClick={() => handleDeleteSection(s.id)}
                    className="shrink-0 p-0.5 rounded transition-opacity opacity-30 hover:opacity-100"
                    style={{ color: '#f87171' }}
                  >
                    <Trash2 size={11} />
                  </button>
                </div>

                {/* Rich text editor */}
                <SectionEditor
                  content={sectionToHtml(s)}
                  onUpdate={(html) => handleSectionContentUpdate(s.id, html)}
                />
              </div>
            ))}

            {/* Add section + finalize */}
            <div className="px-4 py-3 space-y-2">
              <button
                onClick={handleAddBlankSection}
                className="w-full py-2 border border-dashed text-xs font-medium transition-colors"
                style={{ borderColor: '#444', color: c.muted, borderRadius: '2px' }}
                onMouseEnter={(e) => { e.currentTarget.style.borderColor = c.accent; e.currentTarget.style.color = c.accent }}
                onMouseLeave={(e) => { e.currentTarget.style.borderColor = '#444'; e.currentTarget.style.color = c.muted }}
              >
                <Plus size={12} className="inline mr-1" />
                Add Section
              </button>
              {!isFinalized && sections.length > 0 && (
                <button
                  onClick={finalizePosting}
                  disabled={saving}
                  className="w-full py-2 text-xs font-medium rounded transition-colors disabled:opacity-40"
                  style={{ background: placeholderCount > 0 ? c.amber : c.green, color: '#fff' }}
                >
                  {placeholderCount > 0
                    ? `Fill ${placeholderCount} field${placeholderCount !== 1 ? 's' : ''} to finalize`
                    : 'Finalize Posting'}
                </button>
              )}
            </div>
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
                      {tab === 'candidates' && cand.email && cand.status === 'analyzed' && onSendInterviews && (
                        <button
                          onClick={(e) => toggleSelect(cand.id, e)}
                          className="shrink-0 mt-0.5"
                          style={{ color: selectedIds.has(cand.id) ? c.green : c.muted }}
                        >
                          {selectedIds.has(cand.id) ? <CheckSquare size={14} /> : <Square size={14} />}
                        </button>
                      )}
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
