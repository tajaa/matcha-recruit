import { api, ensureFreshToken } from '../../../api/client'
import type { ResearchTask, ResearchInput } from '../../types'
import { BASE } from './_base'

// ── Research tasks ──

export function createResearchTask(projectId: string, body: { name: string; instructions: string }) {
  return api.post<ResearchTask>(`/matcha-work/projects/${projectId}/research-tasks`, body)
}

export function updateResearchTask(projectId: string, taskId: string, body: Partial<{ name: string; instructions: string }>) {
  return api.put<ResearchTask>(`/matcha-work/projects/${projectId}/research-tasks/${taskId}`, body)
}

export function deleteResearchTask(projectId: string, taskId: string) {
  return api.delete(`/matcha-work/projects/${projectId}/research-tasks/${taskId}`)
}

export function addResearchInputs(projectId: string, taskId: string, urls: string[]) {
  return api.post<{ added: number; inputs: ResearchInput[] }>(
    `/matcha-work/projects/${projectId}/research-tasks/${taskId}/inputs`, { urls },
  )
}

export function deleteResearchInput(projectId: string, taskId: string, inputId: string) {
  return api.delete(`/matcha-work/projects/${projectId}/research-tasks/${taskId}/inputs/${inputId}`)
}

export async function runResearchStream(
  projectId: string,
  taskId: string,
  onEvent: (event: { type: string; input_id?: string; message?: string; findings?: Record<string, unknown>; summary?: string; error?: string | null }) => void,
  signal?: AbortSignal,
  captureScreenshot?: boolean,
) {
  const token = await ensureFreshToken()
  const qs = captureScreenshot ? '?capture_screenshot=true' : ''
  const res = await fetch(`${BASE}/matcha-work/projects/${projectId}/research-tasks/${taskId}/run${qs}`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    signal,
  })
  if (!res.ok) throw new Error(`${res.status}`)
  const reader = res.body?.getReader()
  if (!reader) return
  const decoder = new TextDecoder()
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop() || ''
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try { onEvent(JSON.parse(line.slice(6))) } catch {}
      }
    }
  }
}

export async function retryResearchStream(
  projectId: string,
  taskId: string,
  inputId: string,
  onEvent: (event: { type: string; input_id?: string; message?: string }) => void,
) {
  const token = await ensureFreshToken()
  const res = await fetch(`${BASE}/matcha-work/projects/${projectId}/research-tasks/${taskId}/inputs/${inputId}/retry`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) throw new Error(`${res.status}`)
  const reader = res.body?.getReader()
  if (!reader) return
  const decoder = new TextDecoder()
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop() || ''
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try { onEvent(JSON.parse(line.slice(6))) } catch {}
      }
    }
  }
}

export async function followUpResearchStream(
  projectId: string,
  taskId: string,
  inputId: string,
  followUp: string,
  onEvent: (event: { type: string; input_id?: string; message?: string }) => void,
  signal?: AbortSignal,
  captureScreenshot?: boolean,
) {
  const token = await ensureFreshToken()
  const qs = captureScreenshot ? '?capture_screenshot=true' : ''
  const res = await fetch(`${BASE}/matcha-work/projects/${projectId}/research-tasks/${taskId}/inputs/${inputId}/follow-up${qs}`, {
    method: 'POST',
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), 'Content-Type': 'application/json' },
    body: JSON.stringify({ follow_up: followUp }),
    signal,
  })
  if (!res.ok) throw new Error(`${res.status}`)
  const reader = res.body?.getReader()
  if (!reader) return
  const decoder = new TextDecoder()
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop() || ''
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try { onEvent(JSON.parse(line.slice(6))) } catch {}
      }
    }
  }
}

export function stopResearch(projectId: string, taskId: string) {
  return api.post(`/matcha-work/projects/${projectId}/research-tasks/${taskId}/stop`)
}
