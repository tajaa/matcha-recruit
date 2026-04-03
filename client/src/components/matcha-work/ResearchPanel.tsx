import { useState, useRef } from 'react'
import {
  Plus, Trash2, Play, ChevronDown, ChevronRight,
  Globe, Loader2, CheckCircle, Search, AlertCircle, FileOutput, Camera,
} from 'lucide-react'
import type { MWProject, ResearchTask, ResearchResult } from '../../types/matcha-work'
import { useToast } from '../ui'
import {
  createResearchTask, updateResearchTask, deleteResearchTask,
  addResearchInputs, deleteResearchInput, runResearchStream, retryResearchStream,
  followUpResearchStream, stopResearch, getProjectDetail, addProjectSectionNew,
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

function RenderValue({ value }: { value: unknown }) {
  if (value == null) return <span style={{ color: '#6a737d' }}>—</span>

  if (Array.isArray(value)) {
    // Array of objects → render as mini table
    if (value.length > 0 && typeof value[0] === 'object' && value[0] !== null) {
      const keys = [...new Set(value.flatMap(v => Object.keys(v as Record<string, unknown>)))]
      return (
        <div className="overflow-x-auto mt-1">
          <table className="text-[10px] w-full" style={{ borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                {keys.map(k => (
                  <th key={k} className="text-left px-2 py-1 font-medium" style={{ color: '#6a737d', borderBottom: '1px solid #333' }}>
                    {formatKey(k)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {value.map((item, i) => (
                <tr key={i}>
                  {keys.map(k => {
                    const cellVal = (item as Record<string, unknown>)[k]
                    return (
                      <td key={k} className="px-2 py-1 align-top" style={{ color: '#d4d4d4', borderBottom: '1px solid #2a2a2a' }}>
                        {cellVal == null ? '—'
                          : Array.isArray(cellVal) ? cellVal.map((v, j) => (
                              <div key={j} className="text-[10px]">
                                {typeof v === 'object' && v !== null
                                  ? Object.values(v as Record<string, unknown>).join(' · ')
                                  : String(v)}
                              </div>
                            ))
                          : typeof cellVal === 'object' ? Object.entries(cellVal as Record<string, unknown>).map(([ck, cv]) => (
                              <div key={ck} className="text-[10px]">{formatKey(ck)}: {String(cv ?? '—')}</div>
                            ))
                          : String(cellVal)}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )
    }
    // Array of primitives → bullet list
    return (
      <ul className="mt-0.5 space-y-0.5">
        {value.map((v, i) => (
          <li key={i} className="flex items-start gap-1.5 text-[11px]" style={{ color: '#d4d4d4' }}>
            <span className="w-1 h-1 rounded-full bg-zinc-600 mt-1.5 shrink-0" />
            {String(v)}
          </li>
        ))}
      </ul>
    )
  }

  if (typeof value === 'object') {
    // Nested object → render as indented key-value
    return (
      <div className="mt-1 pl-3" style={{ borderLeft: '1px solid #333' }}>
        {Object.entries(value as Record<string, unknown>).map(([k, v]) => (
          <div key={k} className="mb-1">
            <span className="text-[10px] font-medium" style={{ color: '#9ca3af' }}>{formatKey(k)}: </span>
            <span className="text-[11px]" style={{ color: '#d4d4d4' }}>{String(v ?? '—')}</span>
          </div>
        ))}
      </div>
    )
  }

  return <span style={{ color: '#d4d4d4' }}>{String(value)}</span>
}

export default function ResearchPanel({ project, projectId, onUpdate }: Props) {
  const { toast } = useToast()
  const tasks: ResearchTask[] = (project.project_data?.research_tasks as ResearchTask[] | undefined) ?? []
  const [expandedTask, setExpandedTask] = useState<string | null>(tasks[0]?.id ?? null)
  const [creating, setCreating] = useState(false)

  // No polling needed — streaming SSE provides real-time updates

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
      toast('Research task created')
    } catch {
      toast('Failed to create task', 'error')
    }
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

  function flattenValue(value: unknown): string {
    if (value == null) return '—'
    if (Array.isArray(value)) {
      if (value.length > 0 && typeof value[0] === 'object' && value[0] !== null) {
        return value.map((item, i) => {
          const obj = item as Record<string, unknown>
          const parts = Object.entries(obj).map(([k, v]) => {
            if (Array.isArray(v)) return `${formatKey(k)}: ${v.map(x => typeof x === 'object' && x !== null ? Object.values(x as Record<string, unknown>).join(' · ') : String(x)).join(', ')}`
            if (typeof v === 'object' && v !== null) return `${formatKey(k)}: ${Object.entries(v as Record<string, unknown>).map(([ck, cv]) => `${formatKey(ck)}: ${String(cv ?? '—')}`).join(', ')}`
            return `${formatKey(k)}: ${String(v ?? '—')}`
          })
          return parts.join(' | ')
        }).join('\n')
      }
      return value.map(v => String(v)).join(', ')
    }
    if (typeof value === 'object') {
      return Object.entries(value as Record<string, unknown>).map(([k, v]) =>
        `${formatKey(k)}: ${String(v ?? '—')}`
      ).join('\n')
    }
    return String(value)
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
            <label className="flex items-center gap-1.5 mt-1.5 cursor-pointer">
              <input
                type="checkbox"
                checked={captureScreenshot}
                onChange={e => setCaptureScreenshot(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-emerald-500 focus:ring-0 focus:ring-offset-0"
              />
              <Camera size={10} style={{ color: '#6a737d' }} />
              <span className="text-[10px]" style={{ color: '#6a737d' }}>Capture reference screenshot</span>
            </label>
            <div className="flex items-center gap-2 mt-1.5">
              {urlDraft.trim() ? (
                <button
                  onClick={async () => {
                    await handleAddUrls()
                    await handleRun()
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
            {running && (
              <div className="flex items-center gap-2 mt-1.5 px-1">
                <Loader2 size={10} className="animate-spin" style={{ color: '#3b82f6' }} />
                <span className="text-[10px] flex-1" style={{ color: '#93c5fd' }}>{streamStatus || 'Starting...'}</span>
                <button
                  onClick={handleStop}
                  className="text-[10px] font-medium px-2 py-0.5 rounded"
                  style={{ color: '#f87171', background: '#3f1515' }}
                >
                  Stop
                </button>
              </div>
            )}
          </div>

          {/* Results */}
          {completedCount > 1 && (
            <button
              onClick={async () => {
                for (const inp of (task.inputs ?? [])) {
                  const r = getResult(inp.id)
                  if (r && Object.keys(r.findings || {}).length > 0) {
                    await handleAddToProject(inp.url, r.findings, r.summary, r.screenshot_url)
                  }
                }
              }}
              className="flex items-center gap-1 text-[10px] font-medium px-2.5 py-1 rounded transition-colors"
              style={{ color: '#ce9178', background: '#2a2d2e' }}
            >
              <FileOutput size={10} />
              Add All to Project ({completedCount} results)
            </button>
          )}
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
                        {result.screenshot_url && (
                          <a href={result.screenshot_url} target="_blank" rel="noopener noreferrer" className="block mb-2">
                            <img
                              src={result.screenshot_url}
                              alt={`Screenshot of ${formatUrl(inp.url)}`}
                              className="rounded border border-zinc-700 w-full max-h-48 object-cover object-top hover:opacity-90 transition-opacity"
                            />
                          </a>
                        )}
                        {result.summary && (
                          <p className="text-xs mb-2" style={{ color: '#d4d4d4' }}>{result.summary}</p>
                        )}
                        <div className="space-y-2">
                          {Object.entries(result.findings || {}).map(([key, value]) => (
                            <div key={key}>
                              <div className="text-[10px] font-medium mb-0.5" style={{ color: '#ce9178' }}>
                                {formatKey(key)}
                              </div>
                              <div className="text-[11px]">
                                <RenderValue value={value} />
                              </div>
                            </div>
                          ))}
                        </div>
                        {Object.keys(result.findings || {}).length === 0 && (
                          <p className="text-[11px]" style={{ color: '#6a737d' }}>No findings extracted</p>
                        )}
                        {Object.keys(result.findings || {}).length > 0 && (
                          <div className="flex items-center gap-2 mt-2">
                            <button
                              onClick={() => handleAddToProject(inp.url, result.findings, result.summary, result.screenshot_url)}
                              className="flex items-center gap-1 text-[10px] font-medium px-2 py-1 rounded transition-colors"
                              style={{ color: '#ce9178', background: '#2a2d2e' }}
                            >
                              <FileOutput size={10} />
                              Add to Project
                            </button>
                          </div>
                        )}
                        {/* Follow-up research */}
                        {inp.status === 'completed' && (
                          <div className="flex items-center gap-1.5 mt-2">
                            <input
                              value={followUpDraft[inp.id] || ''}
                              onChange={e => setFollowUpDraft(prev => ({ ...prev, [inp.id]: e.target.value }))}
                              onKeyDown={e => { if (e.key === 'Enter' && !running) handleFollowUp(inp.id) }}
                              placeholder="Need more info? e.g. find deposit and lease terms..."
                              disabled={running}
                              className="flex-1 text-[11px] rounded px-2 py-1 border focus:outline-none"
                              style={{ background: '#1e1e1e', color: '#e8e8e8', borderColor: '#444' }}
                            />
                            <button
                              onClick={() => handleFollowUp(inp.id)}
                              disabled={running || !followUpDraft[inp.id]?.trim()}
                              className="flex items-center gap-1 text-[10px] font-medium px-2 py-1 rounded transition-colors disabled:opacity-30"
                              style={{ color: '#fff', background: '#3b82f6' }}
                            >
                              <Search size={10} />
                              Research more
                            </button>
                          </div>
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
