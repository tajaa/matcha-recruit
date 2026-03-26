import { useState, useEffect, useMemo } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../../api/client'
import { Button, Input, Textarea } from '../../components/ui'

// -- Types -------------------------------------------------------------------

interface JurisdictionEntry {
  requirement_id: string; jurisdiction_id: string; state: string; city: string | null
  display_name: string; level: string; title: string; description: string | null
  current_value: string | null; previous_value: string | null; previous_description: string | null
  change_status: 'new' | 'changed' | 'unchanged' | 'needs_review' | null
  effective_date: string | null; source_url: string | null; source_name: string | null
  requires_written_policy: boolean; last_verified_at: string | null; last_changed_at: string | null
}

interface ChangeLogEntry {
  jurisdiction_name: string; field_changed: string; old_value: string | null
  new_value: string | null; changed_at: string; change_source: string
}

interface PolicyDetail {
  id: string; key: string; category_slug: string; category_name: string
  name: string; description: string | null; state_variance: string; enforcing_agency: string | null
  base_weight: number; authority_source_urls: string[] | null; applies_to_levels: string[] | null
  staleness_warning_days: number; staleness_critical_days: number
  update_frequency: string | null; key_group: string | null
  jurisdictions: JurisdictionEntry[]; change_log: ChangeLogEntry[]
}

type EditForm = { title: string; description: string; current_value: string; effective_date: string; source_url: string; source_name: string }

// -- Helpers -----------------------------------------------------------------

function fmtDate(d: string | null) {
  if (!d) return '\u2014'
  return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' })
}

function truncate(s: string | null, len = 60) {
  if (!s) return '\u2014'
  return s.length > len ? s.slice(0, len) + '\u2026' : s
}

const STATUS_STYLE: Record<string, { bg: string; label: string }> = {
  unchanged: { bg: 'bg-zinc-700 text-zinc-400', label: 'Unchanged' },
  changed:   { bg: 'bg-amber-500/15 text-amber-400', label: 'Changed' },
  new:       { bg: 'bg-emerald-500/15 text-emerald-400', label: 'New' },
  needs_review: { bg: 'bg-purple-500/15 text-purple-400', label: 'Review' },
}

function StatusBadge({ status }: { status: string | null }) {
  if (!status) return <span className="text-zinc-600">\u2014</span>
  const s = STATUS_STYLE[status] ?? STATUS_STYLE.unchanged
  return <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${s.bg}`}>{s.label}</span>
}

function VarianceBadge({ variance }: { variance: string }) {
  const v = variance.toLowerCase()
  if (v === 'high') return <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400">{variance}</span>
  if (v === 'moderate') return <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-700/30 text-zinc-300">{variance}</span>
  return <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800/50 text-zinc-500">{variance}</span>
}

// -- Component ---------------------------------------------------------------

export default function PolicyDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [data, setData] = useState<PolicyDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<EditForm>({ title: '', description: '', current_value: '', effective_date: '', source_url: '', source_name: '' })
  const [saving, setSaving] = useState(false)
  const [logOpen, setLogOpen] = useState(false)
  const [search, setSearch] = useState('')

  useEffect(() => {
    if (!id) return
    let cancelled = false
    setLoading(true)
    api.get<PolicyDetail>(`/admin/jurisdictions/policies/${id}`)
      .then((d) => { if (!cancelled) setData(d) })
      .catch(() => { if (!cancelled) setData(null) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [id])

  const filtered = useMemo(() => {
    if (!data) return []
    const q = search.toLowerCase().trim()
    if (!q) return data.jurisdictions
    return data.jurisdictions.filter(
      (j) => j.display_name.toLowerCase().includes(q) || j.title.toLowerCase().includes(q) || (j.current_value || '').toLowerCase().includes(q)
    )
  }, [data, search])

  function startEditing(j: JurisdictionEntry) {
    setEditingId(j.requirement_id)
    setEditForm({
      title: j.title || '', description: j.description || '',
      current_value: j.current_value || '', effective_date: j.effective_date || '',
      source_url: j.source_url || '', source_name: j.source_name || '',
    })
  }

  async function saveEdit() {
    if (!editingId || !data) return
    setSaving(true)
    try {
      const original = data.jurisdictions.find((j) => j.requirement_id === editingId)
      if (!original) return
      const changes: Record<string, string> = {}
      if (editForm.title !== (original.title || '')) changes.title = editForm.title
      if (editForm.description !== (original.description || '')) changes.description = editForm.description
      if (editForm.current_value !== (original.current_value || '')) changes.current_value = editForm.current_value
      if (editForm.effective_date !== (original.effective_date || '')) changes.effective_date = editForm.effective_date
      if (editForm.source_url !== (original.source_url || '')) changes.source_url = editForm.source_url
      if (editForm.source_name !== (original.source_name || '')) changes.source_name = editForm.source_name
      if (Object.keys(changes).length === 0) { setEditingId(null); return }
      const updated = await api.patch<JurisdictionEntry>(`/admin/jurisdictions/requirements/${editingId}`, changes)
      setData({ ...data, jurisdictions: data.jurisdictions.map((j) => j.requirement_id === editingId ? { ...j, ...updated } : j) })
      setEditingId(null)
    } finally { setSaving(false) }
  }

  if (loading) return <div className="text-zinc-500 py-12 text-center">Loading policy...</div>
  if (!data) return <div className="text-zinc-500 py-12 text-center">Policy not found.</div>

  return (
    <div className="space-y-5">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-zinc-500">
        <Link to="/admin/jurisdiction-data" className="hover:text-zinc-200 transition-colors">&larr; Jurisdiction Data</Link>
        <span>/</span>
        <Link to={`/admin/jurisdiction-data/category/${data.category_slug}`} className="hover:text-zinc-200 transition-colors">{data.category_name}</Link>
        <span>/</span>
        <span className="text-zinc-200">{data.name}</span>
      </div>

      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-zinc-100">{data.name}</h1>
        <p className="font-mono text-xs text-zinc-500 mt-1">{data.key}</p>
        <div className="flex items-center gap-2 mt-2">
          <VarianceBadge variance={data.state_variance} />
          {data.enforcing_agency && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-700/30 text-zinc-400">{data.enforcing_agency}</span>
          )}
        </div>
        {data.description && <p className="text-sm text-zinc-400 mt-2 max-w-2xl">{data.description}</p>}
      </div>

      {/* Info cards */}
      <div className="grid grid-cols-3 gap-3">
        <div className="border border-zinc-800 rounded-lg px-4 py-3">
          <div className="text-2xl font-bold text-zinc-100">{data.jurisdictions.length}</div>
          <div className="text-xs text-zinc-500">Jurisdictions</div>
        </div>
        <div className="border border-zinc-800 rounded-lg px-4 py-3">
          <div className="text-sm font-medium text-zinc-200">{data.state_variance}</div>
          <div className="text-xs text-zinc-500">State Variance</div>
        </div>
        <div className="border border-zinc-800 rounded-lg px-4 py-3">
          <div className="text-sm font-medium text-zinc-200">{data.staleness_warning_days}d / {data.staleness_critical_days}d</div>
          <div className="text-xs text-zinc-500">Staleness SLA</div>
        </div>
      </div>

      {/* Search */}
      <input
        type="text"
        placeholder="Filter jurisdictions..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="w-full max-w-md bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-200 text-sm px-3 py-2 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500"
      />

      {/* Jurisdictions table */}
      <div className="border border-zinc-800 rounded-lg overflow-hidden">
        <table className="w-full text-left">
          <thead className="bg-zinc-900/50 text-zinc-400 text-xs uppercase">
            <tr>
              <th className="px-3 py-2">Jurisdiction</th>
              <th className="px-3 py-2">Title</th>
              <th className="px-3 py-2 w-44">Value</th>
              <th className="px-3 py-2 w-28">Eff. Date</th>
              <th className="px-3 py-2 w-20">Status</th>
              <th className="px-3 py-2 w-28">Verified</th>
              <th className="px-3 py-2 w-20">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/50">
            {filtered.map((j) => (
              <JurisdictionRow
                key={j.requirement_id}
                j={j}
                expanded={expandedId === j.requirement_id}
                editing={editingId === j.requirement_id}
                editForm={editForm}
                setEditForm={setEditForm}
                saving={saving}
                onToggle={() => setExpandedId(expandedId === j.requirement_id ? null : j.requirement_id)}
                onEdit={() => startEditing(j)}
                onSave={saveEdit}
                onCancel={() => setEditingId(null)}
              />
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <p className="text-sm text-zinc-600 text-center py-6">
            {search ? `No jurisdictions match "${search}"` : 'No jurisdiction data.'}
          </p>
        )}
      </div>

      {/* Change log */}
      <div className="border border-zinc-800 rounded-lg overflow-hidden">
        <button
          className="w-full flex items-center justify-between px-4 py-3 text-sm text-zinc-300 hover:bg-zinc-800/30 transition-colors"
          onClick={() => setLogOpen(!logOpen)}
        >
          <span className="font-medium">Change Log ({data.change_log.length})</span>
          <span className="text-zinc-500">{logOpen ? '\u25BE' : '\u25B8'}</span>
        </button>
        {logOpen && (
          data.change_log.length === 0 ? (
            <p className="text-sm text-zinc-600 text-center py-6">No changes recorded yet.</p>
          ) : (
            <table className="w-full text-left">
              <thead className="bg-zinc-900/50 text-zinc-400 text-xs uppercase">
                <tr>
                  <th className="px-3 py-2">Jurisdiction</th>
                  <th className="px-3 py-2">Field</th>
                  <th className="px-3 py-2">Old Value</th>
                  <th className="px-3 py-2">New Value</th>
                  <th className="px-3 py-2 w-28">Date</th>
                  <th className="px-3 py-2 w-28">Source</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/50">
                {data.change_log.map((c, i) => (
                  <tr key={i} className="text-xs">
                    <td className="px-3 py-2 text-zinc-300">{c.jurisdiction_name}</td>
                    <td className="px-3 py-2 text-zinc-400 font-mono">{c.field_changed}</td>
                    <td className="px-3 py-2 text-zinc-500" title={c.old_value || ''}>{truncate(c.old_value, 40)}</td>
                    <td className="px-3 py-2 text-zinc-300" title={c.new_value || ''}>{truncate(c.new_value, 40)}</td>
                    <td className="px-3 py-2 text-zinc-500">{fmtDate(c.changed_at)}</td>
                    <td className="px-3 py-2 text-zinc-500">{c.change_source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        )}
      </div>
    </div>
  )
}

// -- Jurisdiction row --------------------------------------------------------

function JurisdictionRow({ j, expanded, editing, editForm, setEditForm, saving, onToggle, onEdit, onSave, onCancel }: {
  j: JurisdictionEntry; expanded: boolean; editing: boolean; editForm: EditForm
  setEditForm: (f: EditForm) => void; saving: boolean
  onToggle: () => void; onEdit: () => void; onSave: () => void; onCancel: () => void
}) {
  if (editing) {
    return (
      <tr>
        <td colSpan={7} className="px-4 py-3 bg-zinc-900/50">
          <div className="space-y-2">
            <div className="text-xs text-zinc-400 font-medium mb-1">{j.display_name}</div>
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
              <Button size="sm" disabled={saving} onClick={onSave}>{saving ? 'Saving...' : 'Save'}</Button>
              <Button variant="ghost" size="sm" onClick={onCancel}>Cancel</Button>
            </div>
          </div>
        </td>
      </tr>
    )
  }

  return (
    <>
      <tr className="cursor-pointer hover:bg-zinc-800/30 transition-colors text-sm" onClick={onToggle}>
        <td className="px-3 py-2 text-zinc-200">{j.display_name}</td>
        <td className="px-3 py-2 text-zinc-300 text-xs">{truncate(j.title, 50)}</td>
        <td className="px-3 py-2 text-xs text-zinc-400 font-mono">{truncate(j.current_value, 30)}</td>
        <td className="px-3 py-2 text-xs text-zinc-500">{fmtDate(j.effective_date)}</td>
        <td className="px-3 py-2"><StatusBadge status={j.change_status} /></td>
        <td className="px-3 py-2 text-xs text-zinc-500">{fmtDate(j.last_verified_at)}</td>
        <td className="px-3 py-2">
          <button
            className="text-xs text-zinc-500 hover:text-zinc-200 transition-colors"
            onClick={(e) => { e.stopPropagation(); onEdit() }}
          >Edit</button>
        </td>
      </tr>
      {expanded && (
        <tr className="bg-zinc-800/20">
          <td colSpan={7} className="px-6 py-3 text-xs text-zinc-400 space-y-2">
            {j.description && <p>{j.description}</p>}
            {j.source_url && (
              <p>
                <span className="text-zinc-500">Source:</span>{' '}
                <a href={j.source_url} target="_blank" rel="noreferrer" className="text-blue-400 hover:underline">{j.source_name || j.source_url}</a>
              </p>
            )}
            {j.change_status === 'changed' && (
              <div className="grid grid-cols-2 gap-4 mt-2 pt-2 border-t border-zinc-700/50">
                <div>
                  <div className="text-zinc-500 text-[10px] uppercase mb-1">Previous</div>
                  <div className="text-zinc-500">{j.previous_value || '\u2014'}</div>
                  {j.previous_description && <div className="text-zinc-600 mt-1">{j.previous_description}</div>}
                </div>
                <div>
                  <div className="text-zinc-400 text-[10px] uppercase mb-1">Current</div>
                  <div className="text-zinc-200">{j.current_value || '\u2014'}</div>
                  {j.description && <div className="text-zinc-400 mt-1">{j.description}</div>}
                </div>
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  )
}
