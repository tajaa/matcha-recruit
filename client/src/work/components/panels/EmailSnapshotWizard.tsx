import { useEffect, useRef, useState } from 'react'
import { Loader2, X } from 'lucide-react'
import type { AgentEmail } from '../../types'
import { agentSnapshotEmails, listProjectTasks, listProjects, type AgentSnapshotResult } from '../../api/matchaWork'
import type { MWProject, MWProjectTask } from '../../types'

export default function EmailSnapshotWizard({ emails, maxEmails, initialIds, onClose }: {
  emails: AgentEmail[]; maxEmails: number; initialIds: string[]; onClose: () => void
}) {
  const [selected, setSelected] = useState<string[]>(() => initialIds.slice(0, Math.max(0, maxEmails)))
  const [projects, setProjects] = useState<MWProject[]>([])
  const [projectId, setProjectId] = useState('')
  const [tasks, setTasks] = useState<MWProjectTask[]>([])
  const [taskId, setTaskId] = useState('')
  const [loadingProjects, setLoadingProjects] = useState(true)
  const [loadingTasks, setLoadingTasks] = useState(false)
  const [saving, setSaving] = useState(false)
  const [result, setResult] = useState<AgentSnapshotResult | null>(null)
  const [error, setError] = useState(initialIds.length > maxEmails ? `Only the first ${maxEmails} emails were preselected.` : '')
  const projectRequest = useRef(0)

  useEffect(() => {
    let active = true
    const requestTracker = projectRequest
    void listProjects('active').then((rows) => { if (active) setProjects(rows) })
      .catch(() => { if (active) setError('Could not load projects.') })
      .finally(() => { if (active) setLoadingProjects(false) })
    return () => { active = false; requestTracker.current++ }
  }, [])

  function chooseProject(id: string) {
    const request = ++projectRequest.current
    setProjectId(id)
    setTaskId('')
    setTasks([])
    setError('')
    if (!id) return
    setLoadingTasks(true)
    void listProjectTasks(id).then((rows) => { if (request === projectRequest.current) setTasks(rows.filter((task) => task.status !== 'cancelled')) })
      .catch(() => { if (request === projectRequest.current) setError('Could not load tasks for this project.') })
      .finally(() => { if (request === projectRequest.current) setLoadingTasks(false) })
  }

  function toggleEmail(id: string) {
    if (selected.includes(id)) { setSelected((ids) => ids.filter((value) => value !== id)); setError(''); return }
    if (selected.length >= maxEmails) { setError(`Select at most ${maxEmails} emails.`); return }
    setSelected((ids) => [...ids, id])
    setError('')
  }

  async function save() {
    if (selected.length === 0 || selected.length > maxEmails || !projectId || !taskId) return
    setSaving(true)
    setError('')
    try { setResult(await agentSnapshotEmails(selected, projectId, taskId)) }
    catch { setError('Could not attach these emails. Check project access and try again.') }
    finally { setSaving(false) }
  }

  return <div className="fixed inset-0 z-[96] flex items-center justify-center bg-black/70 p-4" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
    <section role="dialog" aria-modal="true" aria-label="Send emails to task" className="max-h-[85vh] w-full max-w-xl overflow-y-auto rounded-xl border border-w-line bg-w-surface p-5 text-w-text shadow-2xl">
      <div className="mb-3 flex items-center gap-2"><h2 className="flex-1 text-sm font-semibold">Send emails to task</h2><button onClick={onClose} aria-label="Close"><X size={16} /></button></div>
      <p className="mb-4 text-xs text-w-dim">Attach message snapshots to a task for its project agent. Gmail messages stay unchanged.</p>
      {maxEmails < 1 ? <p className="text-xs text-w-dim">Snapshot limit unavailable. Reopen after email status loads.</p> : <>
        <p className="mb-2 text-xs text-w-dim">Emails ({selected.length}/{maxEmails})</p>
        <div className="mb-4 max-h-36 overflow-y-auto rounded-md border border-w-line">
          {emails.map((email) => <label key={email.id} className="flex cursor-pointer items-center gap-2 border-b border-w-line px-3 py-2 text-xs last:border-b-0"><input type="checkbox" checked={selected.includes(email.id)} onChange={() => toggleEmail(email.id)} /><span className="min-w-0 truncate">{email.subject}</span></label>)}
        </div>
        <label className="mb-3 block text-xs text-w-dim">Project<select value={projectId} disabled={loadingProjects} onChange={(event) => chooseProject(event.target.value)} className="mt-1 block w-full rounded-md border border-w-line bg-w-bg px-3 py-2 text-w-text"><option value="">Choose a project</option>{projects.map((project) => <option key={project.id} value={project.id}>{project.title}</option>)}</select></label>
        <label className="mb-4 block text-xs text-w-dim">Task<select value={taskId} disabled={!projectId || loadingTasks} onChange={(event) => setTaskId(event.target.value)} className="mt-1 block w-full rounded-md border border-w-line bg-w-bg px-3 py-2 text-w-text"><option value="">Choose a task</option>{tasks.map((task) => <option key={task.id} value={task.id}>{task.title}</option>)}</select></label>
        <button onClick={() => void save()} disabled={saving || selected.length === 0 || selected.length > maxEmails || !projectId || !taskId} className="rounded-md bg-w-accent px-3 py-2 text-xs font-semibold text-w-on-accent disabled:opacity-40">{saving ? <Loader2 size={14} className="animate-spin" /> : 'Attach snapshots'}</button>
      </>}
      {error && <p role="alert" className="mt-3 text-xs text-red-400">{error}</p>}
      {result && <div role="status" className="mt-4 space-y-1 border-t border-w-line pt-3 text-xs"><p>{result.files.length} attached, {result.skipped.length} skipped.</p>{result.files.map((file) => <p key={file.id} className="text-w-dim">Attached: {file.filename}</p>)}{result.skipped.map((item) => <p key={item.email_id} className="text-amber-400">Skipped {item.email_id}: {item.reason.replaceAll('_', ' ')}</p>)}</div>}
    </section>
  </div>
}
