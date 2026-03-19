import { useEffect, useState, useCallback, useRef } from 'react'
import { policies } from '../../api/client'
import { Button, Badge, Modal } from '../../components/ui'
import { Upload, Plus, FileText, ExternalLink } from 'lucide-react'
import type { PolicyResponse, PolicyCategory, PolicyStatus } from '../../types/policy'

type Tab = 'all' | 'active' | 'draft' | 'archived'

const STATUS_BADGE: Record<string, 'success' | 'neutral' | 'warning'> = {
  draft: 'neutral',
  active: 'success',
  archived: 'warning',
}

const CATEGORY_LABELS: Record<string, string> = {
  clinical: 'Clinical',
  hr: 'HR',
  compliance: 'Compliance',
  operational: 'Operational',
  safety: 'Safety',
  infection_control: 'Infection Control',
  hipaa: 'HIPAA',
  other: 'Other',
}

const CATEGORIES: PolicyCategory[] = [
  'clinical', 'hr', 'compliance', 'operational',
  'safety', 'infection_control', 'hipaa', 'other',
]

export default function Policies() {
  const [items, setItems] = useState<PolicyResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<Tab>('all')
  const [catFilter, setCatFilter] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [creating, setCreating] = useState(false)
  const [actionLoading, setActionLoading] = useState<string | null>(null)

  // Create form state
  const [formTitle, setFormTitle] = useState('')
  const [formDesc, setFormDesc] = useState('')
  const [formContent, setFormContent] = useState('')
  const [formCategory, setFormCategory] = useState<string>('')
  const [formEffective, setFormEffective] = useState('')
  const [formReview, setFormReview] = useState('')
  const [formStatus, setFormStatus] = useState<PolicyStatus>('draft')
  const [formFile, setFormFile] = useState<File | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const fetchPolicies = useCallback(async () => {
    try {
      setItems(await policies.list())
    } catch {
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchPolicies() }, [fetchPolicies])

  const filtered = items.filter((p) => {
    if (tab !== 'all' && p.status !== tab) return false
    if (catFilter && p.category !== catFilter) return false
    return true
  })

  function resetForm() {
    setFormTitle('')
    setFormDesc('')
    setFormContent('')
    setFormCategory('')
    setFormEffective('')
    setFormReview('')
    setFormStatus('draft')
    setFormFile(null)
  }

  async function handleCreate() {
    if (!formTitle.trim()) return
    setCreating(true)
    setError(null)
    try {
      const fd = new FormData()
      fd.append('title', formTitle)
      if (formDesc) fd.append('description', formDesc)
      if (formContent) fd.append('content', formContent)
      if (formCategory) fd.append('category', formCategory)
      if (formEffective) fd.append('effective_date', formEffective)
      if (formReview) fd.append('review_date', formReview)
      fd.append('status', formStatus)
      if (formFile) fd.append('file', formFile)
      await policies.create(fd)
      setShowCreate(false)
      resetForm()
      fetchPolicies()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create policy')
    } finally {
      setCreating(false)
    }
  }

  async function handleDelete(id: string) {
    if (!window.confirm('Delete this policy?')) return
    setActionLoading(id)
    try {
      await policies.delete(id)
      fetchPolicies()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed')
    } finally {
      setActionLoading(null)
    }
  }

  async function handleActivate(id: string) {
    setActionLoading(id)
    try {
      await policies.update(id, { status: 'active' })
      fetchPolicies()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Activate failed')
    } finally {
      setActionLoading(null)
    }
  }

  async function handleArchive(id: string) {
    setActionLoading(id)
    try {
      await policies.update(id, { status: 'archived' })
      fetchPolicies()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Archive failed')
    } finally {
      setActionLoading(null)
    }
  }

  if (loading) return <p className="text-sm text-zinc-500">Loading...</p>

  return (
    <div>
      {error && (
        <div className="mb-4 p-3 rounded-lg border border-red-800/50 bg-red-900/20 text-sm text-red-400 flex items-center justify-between">
          <span>{error}</span>
          <button type="button" onClick={() => setError(null)} className="text-red-500 hover:text-red-300 text-xs">Dismiss</button>
        </div>
      )}

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100 font-[Space_Grotesk] tracking-tight">Policies</h1>
          <p className="mt-1 text-sm text-zinc-500">Upload, manage, and distribute company policies.</p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="secondary" onClick={() => { resetForm(); setShowCreate(true) }}>
            <Plus className="h-3.5 w-3.5" /> Create Policy
          </Button>
          <Button size="sm" onClick={() => { resetForm(); setFormFile(null); setShowCreate(true); setTimeout(() => fileRef.current?.click(), 100) }}>
            <Upload className="h-3.5 w-3.5" /> Upload Policy
          </Button>
        </div>
      </div>

      {/* Tabs + category filter */}
      <div className="flex items-center justify-between mt-4 border-b border-zinc-800">
        <div className="flex gap-1">
          {(['all', 'active', 'draft', 'archived'] as Tab[]).map((t) => {
            const count = t === 'all' ? items.length : items.filter((p) => p.status === t).length
            return (
              <button
                key={t}
                type="button"
                onClick={() => setTab(t)}
                className={`px-3 py-2 text-xs font-medium capitalize transition-colors border-b-2 -mb-px ${
                  tab === t
                    ? 'border-emerald-500 text-zinc-100'
                    : 'border-transparent text-zinc-500 hover:text-zinc-300'
                }`}
              >
                {t} ({count})
              </button>
            )
          })}
        </div>
        <select
          value={catFilter}
          onChange={(e) => setCatFilter(e.target.value)}
          className="text-xs bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-zinc-400 mb-1"
        >
          <option value="">All Categories</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>{CATEGORY_LABELS[c]}</option>
          ))}
        </select>
      </div>

      {/* List */}
      <div className="mt-3">
        {filtered.length === 0 ? (
          <div className="border border-zinc-800 rounded-lg px-4 py-8 text-center">
            <p className="text-sm text-zinc-600">
              {tab === 'all' && !catFilter ? 'No policies yet. Upload or create one to get started.' : 'No matching policies.'}
            </p>
          </div>
        ) : (
          <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800">
            {filtered.map((p) => (
              <div key={p.id} className="px-4 py-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <FileText className="h-4 w-4 text-zinc-600 shrink-0" />
                      <span className="text-sm font-medium text-zinc-200 truncate">{p.title}</span>
                      <Badge variant={STATUS_BADGE[p.status]}>{p.status}</Badge>
                      {p.category && (
                        <Badge variant="neutral">{CATEGORY_LABELS[p.category] || p.category}</Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-2 mt-1 ml-6">
                      {p.source_type === 'uploaded' && (
                        <span className="text-[10px] text-zinc-500">Uploaded</span>
                      )}
                      <span className="text-[11px] text-zinc-500">v{p.version}</span>
                      {p.effective_date && (
                        <>
                          <span className="text-[11px] text-zinc-700">&middot;</span>
                          <span className="text-[11px] text-zinc-500">Effective {p.effective_date}</span>
                        </>
                      )}
                      {p.original_filename && (
                        <>
                          <span className="text-[11px] text-zinc-700">&middot;</span>
                          <span className="text-[11px] text-zinc-600 truncate max-w-[200px]">{p.original_filename}</span>
                        </>
                      )}
                      {(p.signature_count ?? 0) > 0 && (
                        <>
                          <span className="text-[11px] text-zinc-700">&middot;</span>
                          <span className="text-[11px] text-zinc-500">
                            {p.signed_count}/{p.signature_count} signed
                          </span>
                        </>
                      )}
                      <span className="text-[11px] text-zinc-700">&middot;</span>
                      <span className="text-[11px] text-zinc-600">
                        Updated {new Date(p.updated_at).toLocaleDateString()}
                      </span>
                    </div>
                    {p.description && (
                      <p className="text-[11px] text-zinc-600 mt-1 ml-6 truncate">{p.description}</p>
                    )}
                  </div>

                  <div className="flex items-center gap-1 shrink-0">
                    {p.file_url && (
                      <a
                        href={p.file_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 px-2 py-1 text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors"
                      >
                        <ExternalLink className="h-3 w-3" /> View
                      </a>
                    )}
                    {p.status === 'draft' && (
                      <Button size="sm" variant="ghost" onClick={() => handleActivate(p.id)} disabled={actionLoading === p.id}>
                        Activate
                      </Button>
                    )}
                    {p.status === 'active' && (
                      <Button size="sm" variant="ghost" onClick={() => handleArchive(p.id)} disabled={actionLoading === p.id}>
                        Archive
                      </Button>
                    )}
                    {p.status !== 'active' && (
                      <Button size="sm" variant="ghost" onClick={() => handleDelete(p.id)} disabled={actionLoading === p.id}>
                        Delete
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Create / Upload Modal */}
      <Modal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        title={formFile ? 'Upload Policy' : 'Create Policy'}
        width="md"
      >
        <div className="space-y-4">
          {/* Hidden file input */}
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx,.doc"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) {
                setFormFile(f)
                if (!formTitle) setFormTitle(f.name.replace(/\.[^.]+$/, '').replace(/[-_]/g, ' '))
              }
            }}
          />

          {formFile && (
            <div className="flex items-center gap-2 rounded-lg border border-zinc-700 bg-zinc-800/50 px-3 py-2 text-sm text-zinc-300">
              <FileText className="h-4 w-4 text-zinc-500" />
              <span className="truncate">{formFile.name}</span>
              <button type="button" onClick={() => setFormFile(null)} className="ml-auto text-xs text-zinc-500 hover:text-zinc-300">Remove</button>
            </div>
          )}

          {!formFile && (
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="w-full rounded-lg border border-dashed border-zinc-700 px-4 py-6 text-center text-sm text-zinc-500 hover:border-zinc-500 hover:text-zinc-400 transition-colors"
            >
              <Upload className="h-5 w-5 mx-auto mb-1" />
              Click to upload a PDF or DOCX (optional)
            </button>
          )}

          <div>
            <label className="text-[11px] text-zinc-500 uppercase tracking-wide block mb-1">Title</label>
            <input
              value={formTitle}
              onChange={(e) => setFormTitle(e.target.value)}
              placeholder="e.g., Infection Control Policy"
              className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[11px] text-zinc-500 uppercase tracking-wide block mb-1">Category</label>
              <select
                value={formCategory}
                onChange={(e) => setFormCategory(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200"
              >
                <option value="">Select category...</option>
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>{CATEGORY_LABELS[c]}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-[11px] text-zinc-500 uppercase tracking-wide block mb-1">Status</label>
              <select
                value={formStatus}
                onChange={(e) => setFormStatus(e.target.value as PolicyStatus)}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200"
              >
                <option value="draft">Draft</option>
                <option value="active">Active</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[11px] text-zinc-500 uppercase tracking-wide block mb-1">Effective Date</label>
              <input
                type="date"
                value={formEffective}
                onChange={(e) => setFormEffective(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200"
              />
            </div>
            <div>
              <label className="text-[11px] text-zinc-500 uppercase tracking-wide block mb-1">Review Date</label>
              <input
                type="date"
                value={formReview}
                onChange={(e) => setFormReview(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200"
              />
            </div>
          </div>

          <div>
            <label className="text-[11px] text-zinc-500 uppercase tracking-wide block mb-1">Description</label>
            <input
              value={formDesc}
              onChange={(e) => setFormDesc(e.target.value)}
              placeholder="Brief description of this policy"
              className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200"
            />
          </div>

          {!formFile && (
            <div>
              <label className="text-[11px] text-zinc-500 uppercase tracking-wide block mb-1">Content</label>
              <textarea
                value={formContent}
                onChange={(e) => setFormContent(e.target.value)}
                rows={6}
                placeholder="Paste the policy text here, or upload a file instead"
                className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200"
              />
            </div>
          )}

          <div className="flex gap-2 pt-2">
            <Button onClick={handleCreate} disabled={creating || !formTitle.trim()}>
              {creating ? 'Creating...' : formFile ? 'Upload & Create' : 'Create Policy'}
            </Button>
            <Button variant="ghost" onClick={() => setShowCreate(false)}>Cancel</Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
