import { api } from '../../../api/client'
import { postSSE } from '../../../api/sse'
import type { ResearchTask, ResearchInput } from '../../types'

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

/** A research SSE event. `run` carries findings/summary; retry and follow-up
 *  report progress only. */
export type ResearchStreamEvent = {
  type: string
  input_id?: string
  message?: string
  findings?: Record<string, unknown>
  summary?: string
  error?: string | null
}

export async function runResearchStream(
  projectId: string,
  taskId: string,
  onEvent: (event: ResearchStreamEvent) => void,
  signal?: AbortSignal,
  captureScreenshot?: boolean,
) {
  const qs = captureScreenshot ? '?capture_screenshot=true' : ''
  await postSSE(
    `/matcha-work/projects/${projectId}/research-tasks/${taskId}/run${qs}`,
    undefined,
    (data) => { onEvent(data as ResearchStreamEvent) },
    { signal },
  )
}

export async function retryResearchStream(
  projectId: string,
  taskId: string,
  inputId: string,
  onEvent: (event: ResearchStreamEvent) => void,
) {
  await postSSE(
    `/matcha-work/projects/${projectId}/research-tasks/${taskId}/inputs/${inputId}/retry`,
    undefined,
    (data) => { onEvent(data as ResearchStreamEvent) },
  )
}

export async function followUpResearchStream(
  projectId: string,
  taskId: string,
  inputId: string,
  followUp: string,
  onEvent: (event: ResearchStreamEvent) => void,
  signal?: AbortSignal,
  captureScreenshot?: boolean,
) {
  const qs = captureScreenshot ? '?capture_screenshot=true' : ''
  await postSSE(
    `/matcha-work/projects/${projectId}/research-tasks/${taskId}/inputs/${inputId}/follow-up${qs}`,
    { follow_up: followUp },
    (data) => { onEvent(data as ResearchStreamEvent) },
    { signal },
  )
}

export function stopResearch(projectId: string, taskId: string) {
  return api.post(`/matcha-work/projects/${projectId}/research-tasks/${taskId}/stop`)
}
