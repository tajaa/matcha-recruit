import { api } from '../../../api/client'
import type {
  AgentTask, AgentTaskActionRun, AgentTaskDetail, AgentTaskItemDetail, AgentTaskList, AgentTaskStatusView,
  AgentTasksSummary, IntakeFormAnswer,
} from '../../types'

// Espresso Tasks (`/matcha-work/agent-tasks`), the same API the macOS app's
// Tasks section uses. The server runs each task in the background (finding,
// reading, screening and ranking what fits) and keeps every fact with the
// quote and page it came from; the page shows the tasks and their findings and
// sends follow-ups. Personal Espresso accounts only. A job search is a task
// too (`engine: 'job_search'`): its own view opens inside Tasks.
//
// Every field the server may leave out is optional, so an older or newer
// server never breaks the page.

/** `refine` (free), `more` (1 unit) or `document` (free). */
export type AgentTaskRoundKind = 'refine' | 'more' | 'document'

const BASE = '/matcha-work/agent-tasks'
const taskPath = (id: string) => `${BASE}/${encodeURIComponent(id)}`
const itemPath = (taskId: string, itemId: string) => `${taskPath(taskId)}/items/${encodeURIComponent(itemId)}`

export const listAgentTasks = () => api.get<AgentTaskList>(BASE)
/** Resolve a search's pointer without the recent list's 50-task limit. */
export const getAgentTaskForSearch = (searchId: string) =>
  api.get<AgentTask>(`${BASE}/for-search/${encodeURIComponent(searchId)}`)
/** The sidebar row's counts: running, waiting for the person, finished unseen. */
export const getAgentTasksSummary = () => api.get<AgentTasksSummary>(`${BASE}/summary`)
/** Opening a finished task marks it seen. */
export const getAgentTask = (id: string) => api.get<AgentTaskDetail>(taskPath(id))
/** Cheap to poll; the server also restarts a stalled task when asked. */
export const getAgentTaskStatus = (id: string) => api.get<AgentTaskStatusView>(`${taskPath(id)}/status`)
/** One finding, with the quote and page behind each fact. */
export const getAgentTaskItem = (taskId: string, itemId: string) =>
  api.get<AgentTaskItemDetail>(itemPath(taskId, itemId))
export const updateAgentTaskItem = (taskId: string, itemId: string, patch: { user_state?: string; notes?: string }) =>
  api.patch<AgentTaskItemDetail>(itemPath(taskId, itemId), patch)
/** Refine (free), search more (1 unit) or make a document (free). The request
 *  id makes a retried click the same round. */
export const startAgentTaskRound = (
  taskId: string,
  body: { request_id: string; kind: AgentTaskRoundKind; directive: string; item_ids: string[] },
) => api.post<AgentTaskDetail>(`${taskPath(taskId)}/rounds`, body)
export const cancelAgentTask = (id: string) => api.post<AgentTaskDetail>(`${taskPath(id)}/cancel`)
export const deleteAgentTask = (id: string) => api.delete<{ deleted: boolean }>(taskPath(id))

/** What an action (buy, apply) would do for this finding. Nothing happens
 *  until `confirmAgentTaskAction`. */
export const proposeAgentTaskAction = (taskId: string, itemId: string, action: string, params: Record<string, string>) =>
  api.post<AgentTaskActionRun>(`${itemPath(taskId, itemId)}/actions/${encodeURIComponent(action)}`, { params })
/** Carry out a proposal, once; a retry returns what came of it. */
export const confirmAgentTaskAction = (runId: string) =>
  api.post<AgentTaskActionRun>(`${BASE}/actions/${encodeURIComponent(runId)}/confirm`)
export const cancelAgentTaskAction = (runId: string) =>
  api.post<AgentTaskActionRun>(`${BASE}/actions/${encodeURIComponent(runId)}/cancel`)

/** Submit a form Espresso asked in chat: the task starts with no model run.
 *  A retry gets the same task. */
export const answerAgentTaskForm = (promptId: string, answer: IntakeFormAnswer) =>
  api.post<AgentTask>(`${BASE}/prompts/${encodeURIComponent(promptId)}/answer`, answer)
