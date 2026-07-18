import { Button, Input, Textarea } from '../../ui'
import type { JurisdictionReq, RowContext } from './types'
import { LEVEL_COLORS } from './constants'
import { getCategoryLabel, reqAnchor } from './helpers'

type Props = {
  req: JurisdictionReq
  ctx: RowContext
}

export default function RequirementRow({ req, ctx }: Props) {
  const {
    editingId, editForm, setEditForm, saving, saveEdit, setEditingId,
    reordering, reorderReq, toggleBookmark, startEditing,
    profileFocused, profileEvidence, initialReq,
  } = ctx

  const isFocused = !profileFocused || profileFocused.has(req.category)
  const confidence = profileEvidence?.[req.category]?.confidence

  if (editingId === req.id) {
    return (
      <div key={req.id} className="px-4 py-3 border-t border-zinc-800/30 bg-zinc-900/50 space-y-2">
        <Input label="Title" value={editForm.title} onChange={(e) => setEditForm({ ...editForm, title: e.target.value })} />
        <Textarea label="Description" value={editForm.description} onChange={(e) => setEditForm({ ...editForm, description: e.target.value })} rows={2} placeholder="Optional description" />
        <div className="grid grid-cols-2 gap-2">
          <Input label="Current Value" value={editForm.current_value} onChange={(e) => setEditForm({ ...editForm, current_value: e.target.value })} />
          <Input label="Effective Date" value={editForm.effective_date} onChange={(e) => setEditForm({ ...editForm, effective_date: e.target.value })} placeholder="YYYY-MM-DD" />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Input label="Source Name" value={editForm.source_name} onChange={(e) => setEditForm({ ...editForm, source_name: e.target.value })} />
          <Input label="Source URL" value={editForm.source_url} onChange={(e) => setEditForm({ ...editForm, source_url: e.target.value })} />
        </div>
        <div className="flex gap-2 pt-1">
          <Button size="sm" disabled={saving} onClick={saveEdit}>{saving ? 'Saving...' : 'Save'}</Button>
          <Button variant="ghost" size="sm" onClick={() => setEditingId(null)}>Cancel</Button>
        </div>
      </div>
    )
  }

  const isTarget = req.id === initialReq
  return (
    <div key={req.id} id={reqAnchor(req.id)}
      className={`group flex items-start gap-2 px-4 py-2 border-t border-zinc-800/30 ${!isFocused ? 'opacity-40' : ''} ${isTarget ? 'bg-emerald-500/[0.07] ring-1 ring-inset ring-emerald-500/40' : ''}`}>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm text-zinc-200">{req.title}</p>
          {req.is_bookmarked && <span className="text-[10px] text-amber-400">★</span>}
          {confidence !== undefined && (
            <span className={`w-2 h-2 rounded-full shrink-0 ${
              confidence >= 0.8 ? 'bg-emerald-500' : confidence >= 0.5 ? 'bg-amber-400' : 'bg-red-400'
            }`} title={`Confidence: ${(confidence * 100).toFixed(0)}%`} />
          )}
        </div>
        {req.description && (
          <p className="text-[11px] text-zinc-500 mt-0.5 line-clamp-2">{req.description}</p>
        )}
        <div className="flex items-center gap-2 mt-0.5 flex-wrap">
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-700/50 text-zinc-400">
            {getCategoryLabel(req.category)}
          </span>
          <span className={`text-[10px] px-1.5 py-0.5 rounded ${LEVEL_COLORS[req.jurisdiction_level] || 'text-zinc-400 bg-zinc-500/10'}`}>
            {req.jurisdiction_level}
          </span>
          {req.current_value && <span className="text-[11px] text-zinc-400">{req.current_value}</span>}
          {req.previous_value && <span className="text-[11px] text-zinc-600">Prev: {req.previous_value}</span>}
          {req.effective_date && <span className="text-[11px] text-zinc-600">eff. {req.effective_date}</span>}
          {req.last_verified_at && <span className="text-[11px] text-zinc-600">verified {new Date(req.last_verified_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' })}</span>}
          {req.source_name && (
            req.source_url
              ? <a href={req.source_url} target="_blank" rel="noopener noreferrer" className="text-[11px] text-zinc-600 hover:text-zinc-400 underline">{req.source_name}</a>
              : <span className="text-[11px] text-zinc-600">{req.source_name}</span>
          )}
          {req.source_url_status === 'dead' && (
            <span className="text-[10px] px-1.5 py-0.5 rounded border border-red-500/30 bg-red-500/15 text-red-400"
              title="Source URL failed its last liveness check — kept for re-verification; fix via Edit.">
              dead link
            </span>
          )}
        </div>
      </div>
      <div className="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
        {/* Reorder arrows */}
        <button type="button" onClick={() => reorderReq(req.id, -1)} disabled={reordering}
          className="text-[11px] text-zinc-600 hover:text-zinc-300 px-0.5 transition-colors" title="Move up">▲</button>
        <button type="button" onClick={() => reorderReq(req.id, 1)} disabled={reordering}
          className="text-[11px] text-zinc-600 hover:text-zinc-300 px-0.5 transition-colors" title="Move down">▼</button>
        <button type="button" onClick={() => toggleBookmark(req.id)}
          className="text-[11px] text-zinc-600 hover:text-amber-400 px-1.5 py-0.5 transition-colors">
          {req.is_bookmarked ? 'Unbookmark' : 'Bookmark'}
        </button>
        <button type="button" onClick={() => startEditing(req)}
          className="text-[11px] text-zinc-600 hover:text-zinc-300 px-1.5 py-0.5 transition-colors">
          Edit
        </button>
      </div>
    </div>
  )
}
