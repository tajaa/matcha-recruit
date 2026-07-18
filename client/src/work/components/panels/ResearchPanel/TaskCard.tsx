import {
  Trash2, Play, ChevronDown, ChevronRight,
  Globe, Loader2, CheckCircle, Search, AlertCircle, FileOutput, Camera,
} from 'lucide-react'
import type { TaskCardProps } from './types'
import { formatUrl, formatKey } from './helpers'
import RenderValue from './RenderValue'
import { useTaskCard } from './useTaskCard'

export default function TaskCard({ task, projectId, expanded, onToggle, onUpdate }: TaskCardProps) {
  const {
    instructionsDraft, urlDraft, setUrlDraft, captureScreenshot, setCaptureScreenshot,
    running, followUpDraft, setFollowUpDraft, streamStatus,
    expandedResult, setExpandedResult,
    completedCount, totalCount,
    getResult, handleInstructionsChange, handleAddUrls, handleRun, handleStop,
    handleDeleteTask, handleDeleteInput, handleRetry, handleAddToProject, handleFollowUp,
    pendingOrError,
  } = useTaskCard(task, projectId, onUpdate)

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
