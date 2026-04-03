import { useState, useEffect, useRef } from 'react'
import {
  Plus, Trash2, Play, ChevronDown, ChevronRight,
  Globe, Loader2, CheckCircle, Search, AlertCircle,
} from 'lucide-react'
import type { MWProject, ResearchTask, ResearchResult } from '../../types/matcha-work'
import {
  createResearchTask, updateResearchTask, deleteResearchTask,
  addResearchInputs, deleteResearchInput, runResearch, retryResearchInput,
  getProjectDetail,
} from '../../api/matchaWork'

interface Props {
  project: MWProject
  projectId: string
  onUpdate: (project: MWProject) => void
}

function formatUrl(url: string): string {
  try { return new URL(url).hostname.replace('www.', '') } catch { return url }
}

function formatKey(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

export default function ResearchPanel({ project, projectId, onUpdate }: Props) {
  const tasks: ResearchTask[] = (project.project_data?.research_tasks as ResearchTask[] | undefined) ?? []
  const [expandedTask, setExpandedTask] = useState<string | null>(tasks[0]?.id ?? null)
  const [creating, setCreating] = useState(false)

  // Poll when any input is running
  const hasRunning = tasks.some(t => t.inputs?.some(i => i.status === 'running'))
  useEffect(() => {
    if (!hasRunning) return
    const id = setInterval(async () => {
      try {
        const updated = await getProjectDetail(projectId)
        onUpdate(updated)
      } catch {}
    }, 3000)
    return () => clearInterval(id)
  }, [hasRunning, projectId, onUpdate])

  async function handleCreateTask() {
    setCreating(true)
    try {
      const task = await createResearchTask(projectId, {
        name: 'New Research',
        instructions: '',
      })
      const updated = await getProjectDetail(projectId)
      onUpdate(updated)
      setExpandedTask(task.id)
    } catch {}
    setCreating(false)
  }

  return (
    <div className="flex-1 overflow-y-auto" style={{ background: '#1e1e1e' }}>
      <div className="px-4 py-3 flex items-center justify-between" style={{ borderBottom: '1px solid #333' }}>
        <div className="flex items-center gap-2">
          <Search size={14} style={{ color: '#ce9178' }} />
          <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: '#6a737d' }}>
            Research Tasks ({tasks.length})
          </span>
        </div>
        <button
          onClick={handleCreateTask}
          disabled={creating}
          className="flex items-center gap-1 text-[10px] font-medium px-2.5 py-1 rounded transition-colors"
          style={{ color: '#ce9178' }}
        >
          {creating ? <Loader2 size={10} className="animate-spin" /> : <Plus size={10} />}
          New Task
        </button>
      </div>

      {tasks.length === 0 && (
        <div className="text-center py-12" style={{ color: '#6a737d' }}>
          <Search size={24} className="mx-auto mb-2 opacity-40" />
          <p className="text-xs">No research tasks yet.</p>
          <p className="text-xs mt-1">Create a task to start extracting data from URLs.</p>
        </div>
      )}

      {tasks.map(task => (
        <TaskCard
          key={task.id}
          task={task}
          projectId={projectId}
          expanded={expandedTask === task.id}
          onToggle={() => setExpandedTask(expandedTask === task.id ? null : task.id)}
          onUpdate={onUpdate}
        />
      ))}
    </div>
  )
}


function TaskCard({ task, projectId, expanded, onToggle, onUpdate }: {
  task: ResearchTask; projectId: string; expanded: boolean
  onToggle: () => void; onUpdate: (p: MWProject) => void
}) {
  const [instructionsDraft, setInstructionsDraft] = useState(task.instructions)
  const [urlDraft, setUrlDraft] = useState('')
  const [running, setRunning] = useState(false)
  const [expandedResult, setExpandedResult] = useState<string | null>(null)
  const saveTimer = useRef<ReturnType<typeof setTimeout>>()

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
    setRunning(true)
    try {
      await runResearch(projectId, task.id)
      await refresh()
    } catch {}
    setRunning(false)
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
    try {
      await retryResearchInput(projectId, task.id, inputId)
      await refresh()
    } catch {}
  }

  const pendingOrError = task.inputs?.filter(i => i.status === 'pending' || i.status === 'error').length ?? 0

  return (
    <div style={{ borderBottom: '1px solid #333' }}>
      {/* Header */}
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-2 px-4 py-2.5 text-left transition-colors"
        style={{ background: expanded ? '#252526' : 'transparent' }}
      >
        {expanded ? <ChevronDown size={12} style={{ color: '#6a737d' }} /> : <ChevronRight size={12} style={{ color: '#6a737d' }} />}
        <span className="flex-1 text-xs font-semibold truncate" style={{ color: '#e8e8e8' }}>{task.name}</span>
        <span className="text-[10px]" style={{ color: '#6a737d' }}>
          {completedCount}/{totalCount} done
        </span>
      </button>

      {/* Expanded */}
      {expanded && (
        <div className="px-4 pb-3 space-y-3">
          {/* Instructions — just a prompt */}
          <div>
            <label className="text-[10px] font-medium block mb-1" style={{ color: '#6a737d' }}>What do you want to find?</label>
            <textarea
              value={instructionsDraft}
              onChange={e => handleInstructionsChange(e.target.value)}
              placeholder="e.g. Find out if these apartments have 1br available, what the prices are, and if they offer short term leases"
              rows={3}
              className="w-full text-xs rounded px-2 py-1.5 border focus:outline-none resize-none"
              style={{ background: '#252526', color: '#e8e8e8', borderColor: '#444' }}
            />
          </div>

          {/* URL input */}
          <div>
            <label className="text-[10px] font-medium block mb-1" style={{ color: '#6a737d' }}>URLs (one per line)</label>
            <textarea
              value={urlDraft}
              onChange={e => setUrlDraft(e.target.value)}
              placeholder={"https://example.com\nhttps://another-site.com"}
              rows={2}
              className="w-full text-xs rounded px-2 py-1.5 border focus:outline-none resize-none font-mono"
              style={{ background: '#252526', color: '#e8e8e8', borderColor: '#444' }}
            />
            <div className="flex items-center gap-2 mt-1.5">
              {urlDraft.trim() ? (
                <button
                  onClick={async () => {
                    await handleAddUrls()
                    // Auto-run after adding
                    setRunning(true)
                    try {
                      await runResearch(projectId, task.id)
                      await refresh()
                    } catch {}
                    setRunning(false)
                  }}
                  disabled={running || !instructionsDraft.trim()}
                  className="flex items-center gap-1 text-[10px] font-medium px-2.5 py-1 rounded transition-colors disabled:opacity-40"
                  style={{ color: '#fff', background: '#10b981' }}
                >
                  {running ? <Loader2 size={10} className="animate-spin" /> : <Play size={10} />}
                  {running ? 'Running...' : 'Research'}
                </button>
              ) : pendingOrError > 0 ? (
                <button
                  onClick={handleRun}
                  disabled={running || !instructionsDraft.trim()}
                  className="flex items-center gap-1 text-[10px] font-medium px-2.5 py-1 rounded transition-colors disabled:opacity-40"
                  style={{ color: '#fff', background: '#10b981' }}
                >
                  {running ? <Loader2 size={10} className="animate-spin" /> : <Play size={10} />}
                  Run ({pendingOrError} pending)
                </button>
              ) : null}
              <button onClick={handleDeleteTask} className="ml-auto p-1 rounded opacity-30 hover:opacity-100" style={{ color: '#f87171' }}>
                <Trash2 size={10} />
              </button>
            </div>
          </div>

          {/* Results */}
          {(task.inputs?.length ?? 0) > 0 && (
            <div className="space-y-1.5">
              {task.inputs?.map(inp => {
                const result = getResult(inp.id)
                const isExpanded = expandedResult === inp.id
                return (
                  <div key={inp.id} className="rounded border" style={{ borderColor: '#333', background: '#252526' }}>
                    {/* Row header */}
                    <div className="flex items-center gap-2 px-3 py-2">
                      {/* Status */}
                      <div className="shrink-0">
                        {inp.status === 'running' && <Loader2 size={12} className="animate-spin" style={{ color: '#3b82f6' }} />}
                        {inp.status === 'completed' && <CheckCircle size={12} style={{ color: '#10b981' }} />}
                        {inp.status === 'error' && (
                          <button onClick={() => handleRetry(inp.id)} title={inp.error || 'Click to retry'}>
                            <AlertCircle size={12} style={{ color: '#f87171' }} />
                          </button>
                        )}
                        {inp.status === 'pending' && <div className="w-3 h-3 rounded-full" style={{ background: '#444' }} />}
                      </div>

                      {/* URL */}
                      <a href={inp.url} target="_blank" rel="noopener noreferrer"
                        className="flex items-center gap-1 text-xs hover:underline flex-1 truncate"
                        style={{ color: '#d4d4d4' }}
                      >
                        <Globe size={10} style={{ color: '#6a737d' }} />
                        {formatUrl(inp.url)}
                      </a>

                      {/* Summary preview */}
                      {result?.summary && (
                        <span className="text-[10px] truncate" style={{ color: '#6a737d', maxWidth: 200 }}>
                          {result.summary}
                        </span>
                      )}

                      {/* Expand / Delete */}
                      {result && (
                        <button onClick={() => setExpandedResult(isExpanded ? null : inp.id)} className="shrink-0">
                          {isExpanded
                            ? <ChevronDown size={12} style={{ color: '#6a737d' }} />
                            : <ChevronRight size={12} style={{ color: '#6a737d' }} />}
                        </button>
                      )}
                      <button onClick={() => handleDeleteInput(inp.id)} className="shrink-0 opacity-30 hover:opacity-100" style={{ color: '#f87171' }}>
                        <Trash2 size={10} />
                      </button>
                    </div>

                    {/* Expanded findings */}
                    {isExpanded && result && (
                      <div className="px-3 pb-2 pt-1" style={{ borderTop: '1px solid #333' }}>
                        {result.summary && (
                          <p className="text-xs mb-2" style={{ color: '#d4d4d4' }}>{result.summary}</p>
                        )}
                        <div className="space-y-1">
                          {Object.entries(result.findings || {}).map(([key, value]) => (
                            <div key={key} className="flex gap-2 text-[11px]">
                              <span className="shrink-0 font-medium" style={{ color: '#ce9178', minWidth: 100 }}>
                                {formatKey(key)}
                              </span>
                              <span style={{ color: '#d4d4d4' }}>
                                {typeof value === 'object' ? JSON.stringify(value) : String(value ?? '—')}
                              </span>
                            </div>
                          ))}
                        </div>
                        {Object.keys(result.findings || {}).length === 0 && (
                          <p className="text-[11px]" style={{ color: '#6a737d' }}>No findings extracted</p>
                        )}
                      </div>
                    )}

                    {/* Error display */}
                    {inp.status === 'error' && inp.error && (
                      <div className="px-3 pb-2 text-[10px]" style={{ color: '#f87171' }}>
                        {inp.error}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
