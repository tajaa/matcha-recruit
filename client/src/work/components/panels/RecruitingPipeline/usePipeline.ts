import { useState, useMemo, useRef, useCallback, useEffect } from 'react'
import type { MWProject, RecruitingData } from '../../../types'
import { toggleProjectShortlist, toggleProjectDismiss, rejectProjectCandidate, getProjectDetail, addProjectSectionNew, updateProjectSectionNew, deleteProjectSectionNew, updateProjectPosting } from '../../../api/matchaWork'
import { useToast } from '../../../../components/ui/Toast'
import { extractPlaceholders } from './placeholders'
import type { Tab, SortKey, PlaceholderInfo, RecruitingPipelineProps } from './types'

export function usePipeline({ project, projectId, onUpdate, onSendInterviews, onAnalyzeCandidates, onPromptChat, offerPdfUrl }: RecruitingPipelineProps) {
  const data = (project.project_data || {}) as RecruitingData
  const posting = data.posting || {}
  const candidates = data.candidates || []
  const shortlistIds = new Set(data.shortlist_ids || [])
  const dismissedIds = new Set(data.dismissed_ids || [])
  const sections = project.sections ?? []

  const [tab, setTab] = useState<Tab>('status')
  const [search, setSearch] = useState('')
  const [showDismissed, setShowDismissed] = useState(false)
  const [sortKey, setSortKey] = useState<SortKey>('experience_years')
  const [sortAsc, setSortAsc] = useState(false)
  const [saving, setSaving] = useState(false)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [sendingInterviews, setSendingInterviews] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [positionInput, setPositionInput] = useState('')
  const [showPositionPrompt, setShowPositionPrompt] = useState(false)
  const [reviewInterview, setReviewInterview] = useState<{ id: string; name: string } | null>(null)
  const [rejectTarget, setRejectTarget] = useState<{ id: string; name: string; email: string | null } | null>(null)
  const { toast } = useToast()

  // Section title editing + save feedback
  const [sectionTitleEditing, setSectionTitleEditing] = useState<string | null>(null)
  const [sectionTitleDraft, setSectionTitleDraft] = useState('')
  const [showSaved, setShowSaved] = useState(false)
  const saveTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({})
  const savedTimer = useRef<ReturnType<typeof setTimeout>>(null)

  const isFinalized = !!(posting as Record<string, unknown>).finalized

  const placeholderCount = useMemo(() => {
    const all: PlaceholderInfo[] = []
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

  async function handleRejectConfirm(opts: { reason?: string; customMessage?: string; sendEmail: boolean }) {
    if (!rejectTarget) return
    const resp = await rejectProjectCandidate(projectId, rejectTarget.id, {
      rejectionReason: opts.reason,
      customMessage: opts.customMessage,
      sendEmail: opts.sendEmail,
    })
    onUpdate(resp.project)

    // Distinguish three outcomes: sent ok / silently hidden / email delivery failed
    if (opts.sendEmail && resp.email_sent) {
      toast(`Rejected ${rejectTarget.name} and sent email`, 'success')
    } else if (opts.sendEmail && !resp.email_sent) {
      toast(`Rejected ${rejectTarget.name} — email delivery failed`, 'error')
    } else {
      toast(`Rejected ${rejectTarget.name}`, 'success')
    }
    setRejectTarget(null)
  }

  async function handleRestoreCandidate(candidateId: string) {
    // Restore = remove from dismissed_ids via the existing toggle endpoint.
    try {
      const updated = await toggleProjectDismiss(projectId, candidateId) as unknown as MWProject
      onUpdate(updated)
      toast('Candidate restored', 'info')
    } catch {
      toast('Restore failed', 'error')
    }
  }

  const selectableIds = useMemo(() =>
    candidates.filter((c) => c.status === 'analyzed' && c.email).map((c) => c.id),
    [candidates]
  )

  const hasInterviews = candidates.some((c) => c.interview_id)
  const hasMatchScores = candidates.some((c) => c.match_score != null)

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

  async function handleAnalyze() {
    setAnalyzing(true)
    try {
      await onAnalyzeCandidates!()
      setSortKey('match_score')
      setSortAsc(false)
    } catch {}
    setAnalyzing(false)
  }

  // ── Filtered/sorted candidates ──

  const filteredCandidates = useMemo(() => {
    const q = search.toLowerCase()
    let list = [...candidates]
    if (tab === 'shortlist') list = list.filter((c) => shortlistIds.has(c.id))
    else if (tab === 'interviews') list = list.filter((c) => c.status === 'interview_sent' || c.status === 'interview_completed' || c.status === 'interview_in_progress')
    else if (tab === 'candidates' && !showDismissed) list = list.filter((c) => !dismissedIds.has(c.id))
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
      if (sortKey === 'experience_years' || sortKey === 'match_score') {
        av = (sortKey === 'match_score' ? a.match_score : a.experience_years) ?? 0
        bv = (sortKey === 'match_score' ? b.match_score : b.experience_years) ?? 0
      } else { av = (a[sortKey] ?? '').toString().toLowerCase(); bv = (b[sortKey] ?? '').toString().toLowerCase() }
      if (av < bv) return sortAsc ? -1 : 1
      if (av > bv) return sortAsc ? 1 : -1
      return 0
    })
    return list
  }, [candidates, search, sortKey, sortAsc, tab, shortlistIds, dismissedIds, showDismissed])

  const analyzedCount = candidates.filter((cand) => cand.match_score != null).length
  const interviewedCount = candidates.filter((cand) => cand.status === 'interview_completed').length
  const interviewSentCount = candidates.filter((cand) => cand.interview_id).length

  // Tab unlock logic — can't jump ahead of the current pipeline stage
  const tabUnlocked: Record<Tab, boolean> = {
    status: true,
    posting: true, // always accessible to draft
    candidates: isFinalized, // need finalized posting first
    interviews: candidates.length > 0, // need candidates first
    shortlist: interviewedCount > 0, // need completed interviews
    offer: !!offerPdfUrl,
  }

  const tabs: { key: Tab; label: string; count?: number }[] = [
    { key: 'status', label: 'Status' },
    { key: 'posting', label: 'Posting', count: sections.length },
    { key: 'candidates', label: 'Candidates', count: candidates.length },
    { key: 'interviews', label: 'Interviews', count: interviewSentCount },
    { key: 'shortlist', label: 'Shortlist', count: shortlistIds.size },
    ...(offerPdfUrl ? [{ key: 'offer' as Tab, label: 'Offer' }] : []),
  ]

  // Auto-reset to an unlocked tab if current tab becomes locked
  useEffect(() => {
    if (!tabUnlocked[tab]) setTab('status')
  }, [tabUnlocked[tab]]) // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-switch to offer tab when a draft first appears
  const prevOfferUrl = useRef(offerPdfUrl)
  useEffect(() => {
    if (offerPdfUrl && !prevOfferUrl.current) setTab('offer')
    prevOfferUrl.current = offerPdfUrl
  }, [offerPdfUrl])

  // Contextual guidance based on current state
  const guidance = !isFinalized && sections.length === 0
    ? { text: 'Describe the role in the chat to generate a job posting.', action: 'posting' as Tab }
    : !isFinalized && sections.length > 0
    ? { text: 'Review your posting, fill any placeholders, then finalize it.', action: 'posting' as Tab }
    : isFinalized && candidates.length === 0
    ? { text: 'Posting finalized. Drop resumes in the chat to add candidates.', action: 'candidates' as Tab }
    : candidates.length > 0 && analyzedCount === 0
    ? { text: 'Candidates uploaded. Click "Analyze" to rank them by match score.', action: 'candidates' as Tab }
    : analyzedCount > 0 && interviewSentCount === 0
    ? { text: 'Candidates ranked. Select candidates and send voice interviews.', action: 'candidates' as Tab }
    : interviewSentCount > 0 && interviewedCount === 0
    ? { text: 'Interviews sent. Waiting for candidates to complete their sessions.', action: 'interviews' as Tab }
    : interviewedCount > 0 && shortlistIds.size === 0
    ? { text: 'Interviews complete. Review scores and star your top picks.', action: 'shortlist' as Tab }
    : shortlistIds.size > 0
    ? { text: 'Shortlist ready. Generate offer letters for your top candidates.', action: 'shortlist' as Tab }
    : null

  return {
    // derived project data
    posting, candidates, shortlistIds, dismissedIds, sections,
    // state
    tab, setTab, search, setSearch, showDismissed, setShowDismissed,
    sortKey, setSortKey, sortAsc, setSortAsc, saving, expandedId, setExpandedId,
    selectedIds, sendingInterviews, analyzing, positionInput, setPositionInput,
    showPositionPrompt, setShowPositionPrompt, reviewInterview, setReviewInterview,
    rejectTarget, setRejectTarget,
    sectionTitleEditing, setSectionTitleEditing, sectionTitleDraft, setSectionTitleDraft,
    showSaved,
    // derived
    isFinalized, placeholderCount, selectableIds, hasInterviews, hasMatchScores,
    filteredCandidates, analyzedCount, interviewedCount, interviewSentCount,
    tabUnlocked, tabs, guidance,
    // handlers
    handleSectionContentUpdate, saveSectionTitle, handleDeleteSection, handleAddBlankSection,
    finalizePosting, handleToggleShortlist, handleRejectConfirm, handleRestoreCandidate,
    toggleSelect, toggleSelectAll, handleSendInterviews, handleAnalyze,
  }
}
