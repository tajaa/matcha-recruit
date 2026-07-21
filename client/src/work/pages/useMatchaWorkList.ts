import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { MWThread } from '../types'
import { listChannels } from '../api/channels'
import type { ChannelSummary } from '../api/channels'
import { listThreads, createThread, pinThread, archiveThread, createProjectNew, fetchTaskBoard, createTask, updateTask, deleteTask, dismissAutoTask, listProjects } from '../api/matchaWork'
import type { TaskBoardResponse } from '../api/matchaWork'
import { useMe } from '../../hooks/useMe'
import { ONBOARDING_STORAGE_KEY } from '../components/shell/OnboardingWizard'
import { useWorkBase } from '../routes/WorkSurfaceContext'
import type { MWProject } from '../types'

export type Tab = 'all' | 'active' | 'pinned' | 'archived'

export function useMatchaWorkList() {
  const navigate = useNavigate()
  const base = useWorkBase()
  const { me } = useMe() // auth guard
  const [threads, setThreads] = useState<MWThread[]>([])
  const [channels, setChannels] = useState<ChannelSummary[]>([])
  const [projects, setProjects] = useState<MWProject[]>([])
  const [taskBoard, setTaskBoard] = useState<TaskBoardResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [showTypePicker, setShowTypePicker] = useState(false)
  const [tab, setTab] = useState<Tab>('all')
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')
  const [showOnboarding, setShowOnboarding] = useState(false)

  useEffect(() => {
    if (me?.user?.role !== 'individual') return
    // Backend flag is the source of truth — survives storage wipes across browsers/devices.
    if (me.user.work_onboarded) return
    let seen = false
    try {
      seen = !!localStorage.getItem(ONBOARDING_STORAGE_KEY)
    } catch {
      /* localStorage may be blocked */
    }
    if (!seen) {
      try {
        seen = !!sessionStorage.getItem(ONBOARDING_STORAGE_KEY)
      } catch {
        /* sessionStorage may be blocked too */
      }
    }
    if (!seen) setShowOnboarding(true)
  }, [me])

  async function load() {
    setLoading(true)
    setError('')
    try {
      const status = tab === 'active' ? 'active' : tab === 'archived' ? 'archived' : undefined
      const data = await listThreads(status)
      setThreads(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [tab])

  useEffect(() => {
    listChannels().then(setChannels).catch(() => {})
    listProjects().then(setProjects).catch(() => {})
    // Tasks are a dashboard card now (not a tab), so they load once on mount.
    fetchTaskBoard().then(setTaskBoard).catch(() => {})
  }, [])

  const filtered = tab === 'pinned' ? threads.filter((t) => t.is_pinned) : threads

  async function handleCreate() {
    setCreating(true)
    try {
      const res = await createThread()
      navigate(`${base}/${res.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create')
      setCreating(false)
    }
  }

  async function handleCreateProject(type: 'general' | 'presentation' | 'recruiting' | 'discipline') {
    setShowTypePicker(false)
    setCreating(true)
    const titles: Record<string, string> = {
      general: 'New Project',
      presentation: 'New Presentation',
      recruiting: 'New Job Posting',
      discipline: 'New Disciplinary Action',
    }
    try {
      const res = await createProjectNew(titles[type], type)
      navigate(`${base}/projects/${res.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create')
      setCreating(false)
    }
  }

  async function handlePin(e: React.MouseEvent, t: MWThread) {
    e.stopPropagation()
    try {
      await pinThread(t.id, !t.is_pinned)
      setThreads((prev) =>
        prev.map((x) => (x.id === t.id ? { ...x, is_pinned: !x.is_pinned } : x))
      )
    } catch {}
  }

  async function handleArchive(e: React.MouseEvent, t: MWThread) {
    e.stopPropagation()
    try {
      await archiveThread(t.id)
      setThreads((prev) => prev.filter((x) => x.id !== t.id))
    } catch {}
  }

  // TaskBoard card callbacks — extracted verbatim from the inline JSX props.
  async function handleTaskCreate(body: { title: string; description?: string; due_date?: string; priority?: string }) {
    const newTask = await createTask(body)
    // The card renders even before the board has loaded (or if the
    // fetch failed), so seed a board on null rather than bailing —
    // otherwise the task is created server-side but stays invisible
    // until a reload.
    setTaskBoard((prev) => prev
      ? { ...prev, manual_items: [newTask, ...prev.manual_items], total: prev.total + 1 }
      : { auto_items: [], manual_items: [newTask], dismissed_ids: [], total: 1 })
  }

  async function handleTaskComplete(id: string) {
    await updateTask(id, { status: 'completed' })
    setTaskBoard((prev) => prev ? {
      ...prev,
      manual_items: prev.manual_items.map((t) => t.id === id ? { ...t, status: 'completed' } : t),
    } : prev)
  }

  async function handleTaskUncomplete(id: string) {
    await updateTask(id, { status: 'pending' })
    setTaskBoard((prev) => prev ? {
      ...prev,
      manual_items: prev.manual_items.map((t) => t.id === id ? { ...t, status: 'pending', completed_at: null } : t),
    } : prev)
  }

  async function handleTaskDismiss(category: string, sourceId: string) {
    await dismissAutoTask(category, sourceId)
    setTaskBoard((prev) => prev ? {
      ...prev,
      dismissed_ids: [...prev.dismissed_ids, `${category}:${sourceId}`],
    } : prev)
  }

  async function handleTaskDelete(id: string) {
    await deleteTask(id)
    setTaskBoard((prev) => prev ? {
      ...prev,
      manual_items: prev.manual_items.filter((t) => t.id !== id),
      total: prev.total - 1,
    } : prev)
  }

  const tabs: { key: Tab; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'active', label: 'Active' },
    { key: 'pinned', label: 'Pinned' },
    { key: 'archived', label: 'Archived' },
  ]

  const firstName = (me?.profile?.name || me?.user?.email?.split('@')[0] || '').split(' ')[0]
  const q = query.trim().toLowerCase()
  const searching = q.length > 0
  const matchedProjects = searching ? projects.filter((p) => p.title.toLowerCase().includes(q)) : projects
  const matchedChannels = searching
    ? channels.filter((c) => c.is_member && c.name.toLowerCase().includes(q))
    : channels.filter((c) => c.is_member)
  const matchedThreads = searching ? filtered.filter((t) => t.title.toLowerCase().includes(q)) : filtered
  // Mirror TaskBoard's own dismissal filter (`${category}:${source_id}`) so the
  // header count matches what the board actually renders — and drops as soon as
  // an item is dismissed, since dismissed_ids is updated in state.
  const dismissedSet = new Set(taskBoard?.dismissed_ids ?? [])
  const openAutoCount = (taskBoard?.auto_items ?? []).filter((item) => {
    const sid = (item as unknown as Record<string, unknown>).source_id as string || ''
    return !dismissedSet.has(`${item.category}:${sid}`)
  }).length
  const openTaskCount =
    (taskBoard?.manual_items.filter((t) => t.status !== 'completed').length ?? 0) + openAutoCount

  return {
    base,
    navigate,
    channels,
    taskBoard,
    loading,
    creating,
    showTypePicker,
    setShowTypePicker,
    tab,
    setTab,
    query,
    setQuery,
    error,
    showOnboarding,
    setShowOnboarding,
    tabs,
    firstName,
    searching,
    matchedProjects,
    matchedChannels,
    matchedThreads,
    openTaskCount,
    handleCreate,
    handleCreateProject,
    handlePin,
    handleArchive,
    handleTaskCreate,
    handleTaskComplete,
    handleTaskUncomplete,
    handleTaskDismiss,
    handleTaskDelete,
  }
}
