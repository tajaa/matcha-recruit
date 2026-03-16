import { useEffect, useState, useCallback } from 'react'
import type { FormEvent } from 'react'
import { api } from '../../api/client'
import { Button, Input, Modal, Badge, Select, FileUpload } from '../../components/ui'

// --- Types ---
type HandbookListItem = {
  id: string
  title: string
  status: 'draft' | 'active' | 'archived'
  mode: 'single_state' | 'multi_state'
  source_type: 'template' | 'upload'
  active_version: number
  scope_states: string[]
  pending_changes_count: number
  updated_at: string
  published_at: string | null
  created_at: string
}

type CreateForm = {
  title: string
  mode: 'single_state' | 'multi_state'
  source_type: 'template' | 'upload'
  file: File | null
}

const STATUS_BADGE = {
  draft: 'neutral',
  active: 'success',
  archived: 'warning',
} as const

const MODE_LABEL = {
  single_state: 'Single State',
  multi_state: 'Multi-State',
} as const

const SOURCE_LABEL = {
  template: 'Template',
  upload: 'Upload',
} as const

const INITIAL_FORM: CreateForm = { title: '', mode: 'single_state', source_type: 'template', file: null }

// --- Component ---
export default function Handbooks() {
  const [handbooks, setHandbooks] = useState<HandbookListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState<CreateForm>(INITIAL_FORM)
  const [saving, setSaving] = useState(false)
  const [actionLoading, setActionLoading] = useState<string | null>(null)

  const fetchHandbooks = useCallback(async () => {
    try {
      setHandbooks(await api.get<HandbookListItem[]>('/handbooks'))
    } catch {
      setHandbooks([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchHandbooks() }, [fetchHandbooks])

  async function handleCreate(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      let file_url: string | undefined
      let file_name: string | undefined

      if (form.source_type === 'upload' && form.file) {
        const fd = new FormData()
        fd.append('file', form.file)
        const res = await api.upload<{ url: string; filename: string }>('/handbooks/upload', fd)
        file_url = res.url
        file_name = res.filename
      }

      await api.post('/handbooks', {
        title: form.title,
        mode: form.mode,
        source_type: form.source_type,
        ...(form.source_type === 'template' ? { create_from_template: true } : {}),
        ...(file_url ? { file_url, file_name } : {}),
      })

      setForm(INITIAL_FORM)
      setShowCreate(false)
      fetchHandbooks()
    } finally {
      setSaving(false)
    }
  }

  async function handlePublish(id: string) {
    setActionLoading(id)
    try {
      await api.post(`/handbooks/${id}/publish`)
      fetchHandbooks()
    } finally {
      setActionLoading(null)
    }
  }

  async function handleArchive(id: string) {
    setActionLoading(id)
    try {
      await api.post(`/handbooks/${id}/archive`)
      fetchHandbooks()
    } finally {
      setActionLoading(null)
    }
  }

  async function handleDownload(id: string, title: string) {
    await api.download(`/handbooks/${id}/pdf`, `${title}.pdf`)
  }

  async function handleDistribute(id: string) {
    setActionLoading(id)
    try {
      await api.post(`/handbooks/${id}/distribute`, {})
      fetchHandbooks()
    } finally {
      setActionLoading(null)
    }
  }

  if (loading) return <p className="text-sm text-zinc-500">Loading...</p>

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-100 font-[Space_Grotesk]">Handbooks</h1>
          <p className="mt-1 text-sm text-zinc-500">Create, manage, and distribute employee handbooks.</p>
        </div>
        <Button size="sm" onClick={() => setShowCreate(true)}>Create Handbook</Button>
      </div>

      {/* Handbook list */}
      <div className="mt-5">
        {handbooks.length === 0 ? (
          <div className="border border-zinc-800 rounded-lg px-4 py-8 text-center">
            <p className="text-sm text-zinc-600">No handbooks yet. Create one to get started.</p>
          </div>
        ) : (
          <div className="border border-zinc-800 rounded-lg divide-y divide-zinc-800">
            {handbooks.map((hb) => (
              <div key={hb.id} className="px-4 py-3">
                <div className="flex items-start justify-between gap-3">
                  {/* Left: title + metadata */}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium text-zinc-200 truncate">{hb.title}</p>
                      <Badge variant={STATUS_BADGE[hb.status]}>{hb.status}</Badge>
                      {hb.pending_changes_count > 0 && (
                        <Badge variant="warning">{hb.pending_changes_count} pending</Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-[11px] text-zinc-500">{MODE_LABEL[hb.mode]}</span>
                      <span className="text-[11px] text-zinc-700">&middot;</span>
                      <span className="text-[11px] text-zinc-500">{SOURCE_LABEL[hb.source_type]}</span>
                      <span className="text-[11px] text-zinc-700">&middot;</span>
                      <span className="text-[11px] text-zinc-500">v{hb.active_version}</span>
                      <span className="text-[11px] text-zinc-700">&middot;</span>
                      <span className="text-[11px] text-zinc-600">
                        Updated {new Date(hb.updated_at).toLocaleDateString()}
                      </span>
                      {hb.published_at && (
                        <>
                          <span className="text-[11px] text-zinc-700">&middot;</span>
                          <span className="text-[11px] text-zinc-600">
                            Published {new Date(hb.published_at).toLocaleDateString()}
                          </span>
                        </>
                      )}
                    </div>
                    {hb.scope_states.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1.5">
                        {hb.scope_states.map((st) => (
                          <span
                            key={st}
                            className="inline-block rounded border border-zinc-700 bg-zinc-800/60 px-1.5 py-0.5 text-[10px] text-zinc-400"
                          >
                            {st}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Right: actions */}
                  <div className="flex items-center gap-1 shrink-0">
                    {hb.status === 'draft' && (
                      <button
                        type="button"
                        disabled={actionLoading === hb.id}
                        onClick={() => handlePublish(hb.id)}
                        className="text-xs text-zinc-500 hover:text-zinc-200 px-2 py-1 transition-colors disabled:opacity-50"
                      >
                        Publish
                      </button>
                    )}
                    {hb.status === 'active' && (
                      <button
                        type="button"
                        disabled={actionLoading === hb.id}
                        onClick={() => handleArchive(hb.id)}
                        className="text-xs text-zinc-500 hover:text-zinc-200 px-2 py-1 transition-colors disabled:opacity-50"
                      >
                        Archive
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => handleDownload(hb.id, hb.title)}
                      className="text-xs text-zinc-500 hover:text-zinc-200 px-2 py-1 transition-colors"
                    >
                      Download
                    </button>
                    {hb.status === 'active' && (
                      <button
                        type="button"
                        disabled={actionLoading === hb.id}
                        onClick={() => handleDistribute(hb.id)}
                        className="text-xs text-zinc-500 hover:text-zinc-200 px-2 py-1 transition-colors disabled:opacity-50"
                      >
                        Distribute
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Create Handbook modal */}
      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="Create Handbook" width="sm">
        <form onSubmit={handleCreate} className="space-y-3">
          <Input
            id="hb-title"
            label="Title"
            required
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            placeholder="e.g. 2026 Employee Handbook"
          />
          <Select
            id="hb-mode"
            label="Mode"
            value={form.mode}
            onChange={(e) => setForm({ ...form, mode: e.target.value as CreateForm['mode'] })}
            options={[
              { value: 'single_state', label: 'Single State' },
              { value: 'multi_state', label: 'Multi-State' },
            ]}
          />
          <Select
            id="hb-source"
            label="Source"
            value={form.source_type}
            onChange={(e) => setForm({ ...form, source_type: e.target.value as CreateForm['source_type'], file: null })}
            options={[
              { value: 'template', label: 'Generate from template' },
              { value: 'upload', label: 'Upload existing PDF' },
            ]}
          />
          {form.source_type === 'upload' && (
            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-1.5">PDF File</label>
              <FileUpload
                accept=".pdf"
                onFiles={(files) => setForm({ ...form, file: files[0] ?? null })}
              >
                {form.file ? (
                  <p className="text-sm text-zinc-300">{form.file.name}</p>
                ) : (
                  <p>Drop a PDF here or <span className="text-emerald-400 underline">browse</span></p>
                )}
              </FileUpload>
            </div>
          )}
          <div className="pt-1">
            <Button
              type="submit"
              size="sm"
              disabled={saving || (form.source_type === 'upload' && !form.file)}
            >
              {saving ? 'Creating...' : 'Create Handbook'}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
