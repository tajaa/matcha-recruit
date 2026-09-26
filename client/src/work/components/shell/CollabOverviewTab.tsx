import { useEffect, useState } from 'react'
import { getGithubConnection, getProjectBundle, listCommitSuggestions } from '../../api/matchaWork'
import type { CommitSuggestion, GithubConnection, ProjectBundle } from '../../api/matchaWork'

interface Props { projectId: string; onOpenElements: () => void; onOpenBoard: () => void }

export default function CollabOverviewTab({ projectId, onOpenElements, onOpenBoard }: Props) {
  const [bundle, setBundle] = useState<ProjectBundle | null>(null)
  const [connection, setConnection] = useState<GithubConnection | null>(null)
  const [suggestions, setSuggestions] = useState<CommitSuggestion[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    Promise.all([getProjectBundle(projectId), getGithubConnection(projectId), listCommitSuggestions(projectId)])
      .then(([project, repo, pending]) => {
        if (!active) return
        setBundle(project)
        setConnection(repo)
        setSuggestions(pending)
      })
      .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : 'Could not load overview.') })
    return () => { active = false }
  }, [projectId])

  const openTasks = bundle?.tasks.filter((task) => task.board_column !== 'done').length ?? 0
  const pendingSubtasks = new Set(suggestions.map((item) => item.subtask_id)).size
  return <div className="h-full space-y-4 overflow-y-auto p-4 text-sm text-w-text">
    <header><h2 className="text-lg font-semibold">Overview</h2><p className="text-w-dim">{bundle?.project.title ?? 'Loading project…'}</p></header>
    {error && <p role="alert" className="text-orange-400">{error}</p>}
    <div className="grid gap-3 sm:grid-cols-3">
      <button onClick={onOpenBoard} className="rounded border border-w-line p-3 text-left hover:bg-w-surface"><strong className="block text-lg">{openTasks}</strong> Open tasks</button>
      <button onClick={onOpenBoard} className="rounded border border-w-line p-3 text-left hover:bg-w-surface"><strong className="block text-lg">{bundle?.done_total ?? 0}</strong> Done tasks</button>
      <button onClick={onOpenElements} className="rounded border border-w-line p-3 text-left hover:bg-w-surface"><strong className="block text-lg">{bundle?.elements.length ?? 0}</strong> Elements</button>
    </div>
    <section className="space-y-2 rounded border border-w-line p-3">
      <h3 className="font-semibold">Repository</h3>
      <p className="text-w-dim">{connection?.connected ? connection.repo : 'No repository connected'}</p>
      <button onClick={onOpenElements} className="text-w-accent">Open Elements →</button>
    </section>
    <section className="space-y-2 rounded border border-w-line p-3">
      <h3 className="font-semibold">Commit suggestions · {pendingSubtasks} checklist item{pendingSubtasks === 1 ? '' : 's'}</h3>
      {suggestions.map((suggestion) => <p key={suggestion.id} className="rounded bg-w-surface p-2"><span className="font-medium">{suggestion.commit_short_sha}</span> · {suggestion.commit_message}</p>)}
      {!suggestions.length && <p className="text-w-dim">No pending commit matches.</p>}
      {!!suggestions.length && <button onClick={onOpenElements} className="text-w-accent">Review suggestions →</button>}
    </section>
  </div>
}
