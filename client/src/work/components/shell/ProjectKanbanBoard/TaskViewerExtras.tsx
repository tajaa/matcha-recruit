import { useCallback, useEffect, useState } from 'react'
import {
  getBoardCapabilities,
  getTaskHistory,
  listStagedOutreach,
  startTaskRound,
  summarizeTask,
  updateProjectTask,
} from '../../../api/matchaWork'
import type { MWProjectTask, MWSubtask, MWTaskHistoryEntry } from '../../../types'
import type { StagedOutreachAction } from '../../../api/matchaWork'

interface Props {
  projectId: string
  task: MWProjectTask
  canEdit: boolean
  historyVersion: number
  onPatched: (task: MWProjectTask) => void
  onRoundCreated: (subtask: MWSubtask) => void
}

const models = ['gpt-5.6-sol', 'gpt-5.6-luna', 'gpt-6-astra', 'gpt-5.5']

export default function TaskViewerExtras({ projectId, task, canEdit, historyVersion, onPatched, onRoundCreated }: Props) {
  const [history, setHistory] = useState<MWTaskHistoryEntry[]>([])
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [summary, setSummary] = useState<string | null>(null)
  const [summaryBusy, setSummaryBusy] = useState(false)
  const [roundTitle, setRoundTitle] = useState('')
  const [roundBody, setRoundBody] = useState('')
  const [roundBusy, setRoundBusy] = useState(false)
  const [fieldError, setFieldError] = useState<string | null>(null)
  const [outreach, setOutreach] = useState<StagedOutreachAction[]>([])
  const [outreachState, setOutreachState] = useState<'loading' | 'enabled' | 'not-enabled' | 'unavailable'>('loading')

  const loadHistory = useCallback(() => {
    getTaskHistory(projectId, task.id)
      .then((rows) => { setHistory(rows); setHistoryError(null) })
      .catch((error) => setHistoryError(error instanceof Error ? error.message : 'Could not load task history.'))
  }, [projectId, task.id])

  useEffect(() => { loadHistory() }, [loadHistory, historyVersion])

  useEffect(() => {
    let active = true
    getBoardCapabilities(projectId).then((result) => {
      if (!active) return
      if (!result.capabilities[projectId]?.includes('outreach')) {
        setOutreachState('not-enabled')
        return
      }
      listStagedOutreach(projectId, task.id)
        .then((result) => { if (active) { setOutreach(result.actions); setOutreachState('enabled') } })
        .catch(() => { if (active) setOutreachState('unavailable') })
    }).catch(() => { if (active) setOutreachState('unavailable') })
    return () => { active = false }
  }, [projectId, task.id])

  async function savePrUrl(value: string) {
    const url = value.trim()
    if (url && !/^https?:\/\//i.test(url)) {
      setFieldError('PR URL must start with http:// or https://.')
      return
    }
    setFieldError(null)
    if (url === (task.pr_url ?? '')) return
    try {
      onPatched(await updateProjectTask(projectId, task.id, { pr_url: url || null }))
    } catch (error) {
      setFieldError(error instanceof Error ? error.message : 'Could not save PR URL.')
    }
  }

  async function saveModel(value: string) {
    setFieldError(null)
    try {
      onPatched(await updateProjectTask(projectId, task.id, { autopr_model: value || null }))
    } catch (error) {
      setFieldError(error instanceof Error ? error.message : 'Could not save AutoPR model.')
    }
  }

  async function saveEffort(value: string) {
    setFieldError(null)
    try {
      onPatched(await updateProjectTask(projectId, task.id, { autopr_effort: value || null }))
    } catch (error) {
      setFieldError(error instanceof Error ? error.message : 'Could not save AutoPR effort.')
    }
  }

  async function savePrNumber(value: string) {
    const trimmed = value.trim()
    if (trimmed && (!/^\d+$/.test(trimmed) || Number(trimmed) < 1)) {
      setFieldError('PR number must be a positive integer.')
      return
    }
    setFieldError(null)
    try {
      onPatched(await updateProjectTask(projectId, task.id, { pr_number: trimmed ? Number(trimmed) : null }))
    } catch (error) {
      setFieldError(error instanceof Error ? error.message : 'Could not save PR number.')
    }
  }

  async function openRound() {
    const title = roundTitle.trim()
    if (!title || roundBusy) return
    setRoundBusy(true)
    setFieldError(null)
    try {
      const result = await startTaskRound(projectId, task.id, title, roundBody.trim())
      onRoundCreated(result.subtask)
      setRoundTitle('')
      setRoundBody('')
      loadHistory()
    } catch (error) {
      setFieldError(error instanceof Error ? error.message : 'Could not start a round.')
    } finally {
      setRoundBusy(false)
    }
  }

  return (
    <div className="space-y-4 border-t border-w-line pt-4 text-xs text-w-text">
      {canEdit && (
        <section className="space-y-2">
          <h3 className="font-semibold">PR and AutoPR</h3>
          <label className="block text-w-dim">Pull request URL
            <input
              key={task.pr_url ?? ''}
              defaultValue={task.pr_url ?? ''}
              onBlur={(event) => void savePrUrl(event.target.value)}
              placeholder="https://github.com/…/pull/123"
              className="mt-1 w-full rounded border border-w-line bg-w-surface px-2 py-1.5 text-w-text"
            />
          </label>
          {task.pr_url && <a href={task.pr_url} target="_blank" rel="noopener noreferrer" className="text-w-accent underline">Open PR{task.pr_number ? ` #${task.pr_number}` : ''}</a>}
          <label className="block text-w-dim">PR number
            <input
              key={task.pr_number ?? ''}
              defaultValue={task.pr_number ?? ''}
              inputMode="numeric"
              onBlur={(event) => { if (event.target.value !== String(task.pr_number ?? '')) void savePrNumber(event.target.value) }}
              className="mt-1 w-full rounded border border-w-line bg-w-surface px-2 py-1.5 text-w-text"
            />
          </label>
          <label className="block text-w-dim">AutoPR model
            <select
              value={task.autopr_model ?? ''}
              onChange={(event) => void saveModel(event.target.value)}
              className="mt-1 w-full rounded border border-w-line bg-w-surface px-2 py-1.5 text-w-text"
            >
              <option value="">Auto</option>
              {models.map((model) => <option key={model} value={model}>{model}</option>)}
            </select>
          </label>
          <label className="block text-w-dim">AutoPR effort
            <select value={task.autopr_effort ?? ''} onChange={(event) => void saveEffort(event.target.value)} className="mt-1 w-full rounded border border-w-line bg-w-surface px-2 py-1.5 text-w-text">
              <option value="">Auto</option>
              {['low', 'medium', 'high', 'xhigh'].map((effort) => <option key={effort} value={effort}>{effort}</option>)}
            </select>
          </label>
          {task.autopr_runtime_source && <p className="text-w-dim">Runtime source: {task.autopr_runtime_source}</p>}
        </section>
      )}

      {canEdit && (
        <section className="space-y-2">
          <h3 className="font-semibold">New round</h3>
          <input value={roundTitle} onChange={(event) => setRoundTitle(event.target.value)} placeholder="Suggested fix" className="w-full rounded border border-w-line bg-w-surface px-2 py-1.5" />
          <textarea value={roundBody} onChange={(event) => setRoundBody(event.target.value)} placeholder="Kickoff note (optional)" rows={2} className="w-full rounded border border-w-line bg-w-surface px-2 py-1.5" />
          <button onClick={() => void openRound()} disabled={!roundTitle.trim() || roundBusy} className="rounded bg-w-accent px-2 py-1 text-white disabled:opacity-50">{roundBusy ? 'Starting…' : 'Start round'}</button>
        </section>
      )}

      {canEdit && (
        <section className="space-y-2">
          <button
            onClick={async () => {
              setSummaryBusy(true)
              try { setSummary((await summarizeTask(projectId, task.id)).summary) }
              catch (error) { setFieldError(error instanceof Error ? error.message : 'Could not summarize task.') }
              finally { setSummaryBusy(false) }
            }}
            disabled={summaryBusy}
            className="rounded border border-w-line px-2 py-1.5 disabled:opacity-50"
          >{summaryBusy ? 'Summarizing…' : 'Summarize task'}</button>
          {summary && <p className="whitespace-pre-wrap rounded bg-w-surface p-2">{summary}</p>}
        </section>
      )}

      <section className="space-y-2">
        <h3 className="font-semibold">History</h3>
        {historyError && <p role="alert" className="text-orange-400">{historyError}</p>}
        {history.map((event) => (
          <div key={event.id} className="border-l border-w-line pl-2 text-w-dim">
            <span className="font-medium text-w-text">{event.event_type.replaceAll('_', ' ')}</span>
            {event.actor_name && <span> · {event.actor_name}</span>}
            <time className="ml-1" dateTime={event.created_at}>{new Date(event.created_at).toLocaleString()}</time>
            {typeof event.metadata?.body === 'string' && <p className="whitespace-pre-wrap">{event.metadata.body}</p>}
            {typeof event.metadata?.reason === 'string' && <p className="whitespace-pre-wrap">{event.metadata.reason}</p>}
          </div>
        ))}
      </section>

      <section className="space-y-2">
        <h3 className="font-semibold">Outreach</h3>
        {outreachState === 'loading' && <p className="text-w-dim">Checking board access…</p>}
        {outreachState === 'not-enabled' && <p className="text-w-dim">Outreach is not enabled for this board.</p>}
        {outreachState === 'unavailable' && <p role="alert" className="text-orange-400">Could not load outreach status.</p>}
        {outreachState === 'enabled' && (outreach.length ? outreach.map((action) => (
          <div key={action.id} className="rounded border border-w-line p-2">
            <p className="font-medium">{action.kind} · {action.state}</p>
            {action.to && <p className="text-w-dim">To: {action.to}</p>}
            {action.subject && <p>{action.subject}</p>}
            {action.detail && <p className="text-w-dim">{action.detail}</p>}
          </div>
        )) : <p className="text-w-dim">No outreach staged for this task.</p>)}
      </section>
      {fieldError && <p role="alert" className="text-orange-400">{fieldError}</p>}
    </div>
  )
}
