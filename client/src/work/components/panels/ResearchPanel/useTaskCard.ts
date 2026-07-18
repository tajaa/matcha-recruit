import { useState, useRef } from 'react'
import type { MWProject, ResearchTask, ResearchResult } from '../../../types'
import { useToast } from '../../../../components/ui'
import {
  updateResearchTask, deleteResearchTask, addResearchInputs, deleteResearchInput,
  runResearchStream, retryResearchStream, followUpResearchStream, stopResearch,
  getProjectDetail, addProjectSectionNew,
} from '../../../api/matchaWork'
import { formatUrl, formatKey, flattenValue } from './helpers'

export function useTaskCard(task: ResearchTask, projectId: string, onUpdate: (p: MWProject) => void) {
  const { toast } = useToast()
  const [instructionsDraft, setInstructionsDraft] = useState(task.instructions)
  const [urlDraft, setUrlDraft] = useState('')
  const [captureScreenshot, setCaptureScreenshot] = useState(true)
  const [running, setRunning] = useState(false)
  const [followUpDraft, setFollowUpDraft] = useState<Record<string, string>>({})
  const [streamStatus, setStreamStatus] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const [expandedResult, setExpandedResult] = useState<string | null>(null)
  const saveTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  const completedCount = task.inputs?.filter(i => i.status === 'completed').length ?? 0
  const totalCount = task.inputs?.length ?? 0
  const results = task.results ?? []

  function getResult(inputId: string): ResearchResult | undefined {
    return results.find(r => r.input_id === inputId)
  }

  async function refresh() {
    const updated = await getProjectDetail(projectId)
    onUpdate(updated)
  }

  function handleInstructionsChange(val: string) {
    setInstructionsDraft(val)
    clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(async () => {
      try {
        await updateResearchTask(projectId, task.id, { instructions: val })
      } catch {}
    }, 1000)
  }

  async function handleAddUrls() {
    const urls = urlDraft.split('\n').map(u => u.trim()).filter(Boolean)
    if (urls.length === 0) return
    try {
      await addResearchInputs(projectId, task.id, urls)
      setUrlDraft('')
      await refresh()
    } catch {}
  }

  async function handleRun() {
    const abort = new AbortController()
    abortRef.current = abort
    setRunning(true)
    setStreamStatus(null)
    try {
      await runResearchStream(projectId, task.id, async (event) => {
        if (event.type === 'status') {
          setStreamStatus(event.message || null)
        } else if (event.type === 'complete' || event.type === 'error') {
          setStreamStatus(null)
          await refresh()
        } else if (event.type === 'done') {
          setStreamStatus(null)
          await refresh()
        }
      }, abort.signal, captureScreenshot)
    } catch {
      // AbortError or network error — expected on cancel
    }
    abortRef.current = null
    setRunning(false)
    setStreamStatus(null)
    await refresh()
  }

  async function handleStop() {
    abortRef.current?.abort()
    try {
      await stopResearch(projectId, task.id)
      await refresh()
    } catch {}
  }

  async function handleDeleteTask() {
    try {
      await deleteResearchTask(projectId, task.id)
      await refresh()
    } catch {}
  }

  async function handleDeleteInput(inputId: string) {
    try {
      await deleteResearchInput(projectId, task.id, inputId)
      await refresh()
    } catch {}
  }

  async function handleRetry(inputId: string) {
    setRunning(true)
    setStreamStatus(null)
    try {
      await retryResearchStream(projectId, task.id, inputId, async (event) => {
        if (event.type === 'status') {
          setStreamStatus(event.message || null)
        } else if (event.type === 'complete' || event.type === 'error' || event.type === 'done') {
          setStreamStatus(null)
          await refresh()
        }
      })
    } catch {}
    setRunning(false)
    setStreamStatus(null)
  }

  async function handleAddToProject(inputUrl: string, findings: Record<string, unknown>, summary?: string, screenshotUrl?: string) {
    const title = formatUrl(inputUrl)
    let html = `<h2>${title}</h2>`
    if (screenshotUrl) html += `<img src="${screenshotUrl}" alt="${title}" style="max-width:100%;border-radius:8px;margin:8px 0;" />`
    if (summary) html += `<p>${summary}</p>`
    for (const [key, value] of Object.entries(findings)) {
      const text = flattenValue(value)
      html += `<h3>${formatKey(key)}</h3>`
      // Split multiline values into paragraphs
      const lines = text.split('\n').filter(Boolean)
      if (lines.length > 1) {
        html += '<ul>' + lines.map(l => `<li>${l}</li>`).join('') + '</ul>'
      } else {
        html += `<p>${text}</p>`
      }
    }
    try {
      await addProjectSectionNew(projectId, { title, content: html })
      await refresh()
      toast(`Added "${title}" to project sections`)
    } catch {
      toast('Failed to add to project', 'error')
    }
  }

  async function handleFollowUp(inputId: string) {
    const text = followUpDraft[inputId]?.trim()
    if (!text) return
    const abort = new AbortController()
    abortRef.current = abort
    setRunning(true)
    setStreamStatus(null)
    try {
      await followUpResearchStream(projectId, task.id, inputId, text, async (event) => {
        if (event.type === 'status') setStreamStatus(event.message || null)
        else if (event.type === 'complete' || event.type === 'error' || event.type === 'done') {
          setStreamStatus(null)
          await refresh()
        }
      }, abort.signal, captureScreenshot)
    } catch {}
    abortRef.current = null
    setRunning(false)
    setStreamStatus(null)
    setFollowUpDraft(prev => ({ ...prev, [inputId]: '' }))
    await refresh()
  }

  const pendingOrError = task.inputs?.filter(i => i.status === 'pending' || i.status === 'error').length ?? 0

  return {
    instructionsDraft, urlDraft, setUrlDraft, captureScreenshot, setCaptureScreenshot,
    running, followUpDraft, setFollowUpDraft, streamStatus,
    expandedResult, setExpandedResult,
    completedCount, totalCount,
    getResult, handleInstructionsChange, handleAddUrls, handleRun, handleStop,
    handleDeleteTask, handleDeleteInput, handleRetry, handleAddToProject, handleFollowUp,
    pendingOrError,
  }
}
