import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../../../api/client'
import {
  acceptCommitSuggestion, createProjectElement, deleteProjectElement, dismissCommitSuggestion,
  getGithubConnection, listCommitSuggestions, listProjectElements, patchProjectElement,
  putGithubConnection, scanGithubCommits,
} from '../../api/matchaWork'
import type { CommitSuggestion, GithubConnection, ProjectElement } from '../../api/matchaWork'
import { autoSyncFromGithubIfStale, syncGithubNow } from '../../utils/githubAutoSync'
import ElementDetail from './ElementDetail'

interface Props { projectId: string; canEdit: boolean }

export default function ProjectElementsTab({ projectId, canEdit }: Props) {
  const [elements, setElements] = useState<ProjectElement[]>([])
  const [connection, setConnection] = useState<GithubConnection | null>(null)
  const [repo, setRepo] = useState('')
  const [branch, setBranch] = useState('')
  const [suggestions, setSuggestions] = useState<CommitSuggestion[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [newName, setNewName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [wizardStep, setWizardStep] = useState(0)
  const [wizardDismissed, setWizardDismissed] = useState(() => localStorage.getItem(`espresso-elements-wizard:${projectId}`) === '1')

  const refresh = useCallback(async () => {
    const [rows, pending] = await Promise.all([listProjectElements(projectId), listCommitSuggestions(projectId)])
    setElements(rows.filter((element) => element.kind !== '_repository_snapshot'))
    setSuggestions(pending)
  }, [projectId])

  useEffect(() => {
    let active = true
    Promise.all([getGithubConnection(projectId), listProjectElements(projectId), listCommitSuggestions(projectId)])
      .then(async ([connected, rows, pending]) => {
        if (!active) return
        setConnection(connected)
        setRepo(connected.repo ?? '')
        setBranch(connected.branch ?? '')
        setElements(rows.filter((element) => element.kind !== '_repository_snapshot'))
        setSuggestions(pending)
        const synced = await autoSyncFromGithubIfStale(projectId, connected.connected)
        if (active && synced) await refresh()
      })
      .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : 'Could not load elements.') })
    return () => { active = false }
  }, [projectId, refresh])

  async function connect() {
    if (busy) return
    setBusy(true); setError(null)
    try {
      const result = await putGithubConnection(projectId, repo.trim(), branch.trim() || null)
      setConnection(result)
      setRepo(result.repo ?? '')
      setBranch(result.branch ?? '')
      if (result.connected) await syncGithubNow(projectId)
      await refresh()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not update repository.') }
    finally { setBusy(false) }
  }

  async function scan() {
    setBusy(true); setError(null)
    try {
      const result = await scanGithubCommits(projectId, true)
      if (result.scanned > 0) await refresh()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Commit scan failed.') }
    finally { setBusy(false) }
  }

  async function resolveSuggestion(suggestion: CommitSuggestion, kind: 'accept' | 'dismiss') {
    setSuggestions((rows) => rows.filter((row) => row.id !== suggestion.id))
    try {
      if (kind === 'accept') await acceptCommitSuggestion(projectId, suggestion.id)
      else await dismissCommitSuggestion(projectId, suggestion.id)
    } catch (cause) {
      await refresh()
      if (!(cause instanceof ApiError && cause.status === 404)) setError(cause instanceof Error ? cause.message : 'Could not resolve suggestion.')
    }
  }

  const selected = elements.find((element) => element.id === selectedId)
  const suggestionsByTask = new Map<string, CommitSuggestion[]>()
  suggestions.forEach((suggestion) => {
    const rows = suggestionsByTask.get(suggestion.task_id) ?? []
    rows.push(suggestion)
    suggestionsByTask.set(suggestion.task_id, rows)
  })
  if (selected) return <ElementDetail
    key={selected.id}
    projectId={projectId}
    element={selected}
    canEdit={canEdit}
    onBack={() => setSelectedId(null)}
    parentError={error}
    onSave={async (patch) => {
      try {
        const updated = await patchProjectElement(projectId, selected.id, patch)
        setElements((rows) => rows.map((row) => row.id === selected.id ? updated : row))
      } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not save element.') }
    }}
    onDelete={async () => {
      try { await deleteProjectElement(projectId, selected.id); setSelectedId(null); await refresh() }
      catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not delete element.') }
    }}
  />

  const wizard = ['Connect a GitHub repository', 'Create a code element', 'Set its file globs', 'Scan commits for ticket suggestions']
  return (
    <div className="h-full space-y-4 overflow-y-auto p-4 text-sm text-w-text">
      <header><h2 className="text-lg font-semibold">Elements</h2><p className="text-xs text-w-dim">Code areas, files, notes, and tickets for this project.</p></header>
      {error && <p role="alert" className="text-orange-400">{error}</p>}
      {!wizardDismissed && elements.length === 0 && <div className="rounded border border-w-accent/40 bg-w-accent/5 p-3">
        <p className="text-xs text-w-dim">Getting started · {wizardStep + 1} of 4</p>
        <p className="font-medium">{wizard[wizardStep]}</p>
        <div className="mt-2 flex gap-3"><button onClick={() => setWizardStep((step) => Math.min(3, step + 1))} disabled={wizardStep === 3} className="text-w-accent disabled:opacity-50">Next</button><button onClick={() => { localStorage.setItem(`espresso-elements-wizard:${projectId}`, '1'); setWizardDismissed(true) }} className="text-w-dim">Done</button></div>
      </div>}
      <section className="space-y-2 rounded border border-w-line p-3">
        <h3 className="font-semibold">GitHub repository</h3>
        <p className="text-xs text-w-dim">{connection?.connected ? `Connected to ${connection.repo}` : 'No repository connected.'}</p>
        {canEdit && <div className="flex flex-wrap gap-2">
          <input value={repo} onChange={(event) => setRepo(event.target.value)} placeholder="owner/repository" className="min-w-0 flex-1 rounded border border-w-line bg-w-surface p-1.5" />
          <input value={branch} onChange={(event) => setBranch(event.target.value)} placeholder="Branch" className="w-28 rounded border border-w-line bg-w-surface p-1.5" />
          <button disabled={busy || (!repo.trim() && !connection?.connected)} onClick={() => void connect()} className="rounded bg-w-accent px-2 text-white disabled:opacity-50">Save connection</button>
          {connection?.connected && <button disabled={busy} onClick={() => { setRepo(''); void putGithubConnection(projectId, '').then((result) => { setConnection(result); setElements([]); setSuggestions([]) }).catch((cause) => setError(String(cause))) }} className="text-red-400">Disconnect</button>}
          {connection?.connected && <button disabled={busy} onClick={() => void scan()} className="rounded border border-w-line px-2">Scan commits</button>}
          {connection?.connected && <button disabled={busy} onClick={() => void syncGithubNow(projectId).then(refresh).catch((cause) => setError(String(cause)))} className="rounded border border-w-line px-2">Sync code</button>}
        </div>}
      </section>
      {canEdit && <section className="flex gap-2">
        <input value={newName} onChange={(event) => setNewName(event.target.value)} placeholder="New element name" className="min-w-0 flex-1 rounded border border-w-line bg-w-surface p-1.5" />
        <button disabled={!newName.trim()} onClick={() => void createProjectElement(projectId, { name: newName.trim() }).then((element) => { setNewName(''); setElements((rows) => [...rows, element]); setSelectedId(element.id) }).catch((cause) => setError(String(cause)))} className="rounded bg-w-accent px-2 text-white disabled:opacity-50">Create element</button>
      </section>}
      <section className="space-y-2">
        {elements.map((element) => <button key={element.id} onClick={() => setSelectedId(element.id)} className="block w-full rounded border border-w-line p-3 text-left hover:bg-w-surface">
          <strong>{element.name}</strong><span className="ml-2 text-xs text-w-dim">{element.kind ?? 'component'}</span>
          {element.description && <p className="text-xs text-w-dim">{element.description}</p>}
        </button>)}
        {!elements.length && <p className="text-w-dim">No elements yet.</p>}
      </section>
      <section className="space-y-2 rounded border border-w-line p-3">
        <h3 className="font-semibold">Commit suggestions</h3>
        {[...suggestionsByTask].map(([taskId, rows]) => <div key={taskId} className="space-y-1"><h4 className="text-xs font-medium text-w-dim">Task {taskId}</h4>{rows.map((suggestion) => <div key={suggestion.id} className="rounded bg-w-surface p-2">
          <p>{suggestion.commit_short_sha} · {suggestion.commit_message}</p>
          {suggestion.reasoning && <p className="text-xs text-w-dim">{suggestion.reasoning}</p>}
          {canEdit && <div className="mt-1 flex gap-3"><button onClick={() => void resolveSuggestion(suggestion, 'accept')} className="text-w-accent">Accept</button><button onClick={() => void resolveSuggestion(suggestion, 'dismiss')} className="text-w-dim">Dismiss</button></div>}
        </div>)}</div>)}
        {!suggestions.length && <p className="text-w-dim">No pending suggestions.</p>}
      </section>
    </div>
  )
}
