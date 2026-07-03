import { useState } from 'react'
import { Layout, Trash2 } from 'lucide-react'
import { api } from '../../../api/client'
import type { Template } from './types'

export function TemplatesTab({
  templates,
  onChange,
  onPickTemplate,
}: {
  templates: Template[]
  onChange: () => Promise<void> | void
  onPickTemplate: (t: Template) => Promise<void> | void
}) {
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [pre, setPre] = useState('')
  const [html, setHtml] = useState('')

  async function save() {
    if (!name.trim()) return
    await api.post('/admin/newsletter/templates', {
      name: name.trim(), description: desc || undefined,
      content_html: html || undefined, preheader: pre || undefined,
    })
    setName(''); setDesc(''); setPre(''); setHtml('')
    await onChange()
  }

  async function remove(id: string) {
    if (!confirm('Delete template? Existing newsletters built from it are unaffected.')) return
    await api.delete(`/admin/newsletter/templates/${id}`)
    await onChange()
  }

  return (
    <div className="grid lg:grid-cols-[1fr_360px] gap-6 max-w-6xl">
      <div className="space-y-3">
        <p className="text-xs text-zinc-400">Saved templates seed new newsletters with proven content.</p>
        {templates.length === 0 && <p className="text-zinc-500 text-sm py-4">No templates yet.</p>}
        {templates.map((t) => (
          <div key={t.id} className="rounded-xl border border-zinc-800 px-4 py-3 flex items-center gap-3">
            <Layout size={14} className="text-zinc-500 shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-sm text-zinc-200 truncate">{t.name}</p>
              {t.description && <p className="text-[11px] text-zinc-500 truncate">{t.description}</p>}
            </div>
            <button onClick={() => onPickTemplate(t)} className="text-xs text-emerald-400 hover:text-emerald-300">Use →</button>
            <button onClick={() => remove(t.id)} className="text-zinc-500 hover:text-red-400"><Trash2 size={13} /></button>
          </div>
        ))}
      </div>
      <div className="rounded-xl border border-zinc-800 p-4 space-y-3 self-start">
        <p className="text-[10px] text-zinc-500 uppercase tracking-wider">Save current as template</p>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Template name" className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-900 text-sm text-zinc-200 placeholder-zinc-500 outline-none" />
        <input value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Description (optional)" className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-900 text-sm text-zinc-200 placeholder-zinc-500 outline-none" />
        <input value={pre} onChange={(e) => setPre(e.target.value)} placeholder="Preheader (optional)" className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-900 text-sm text-zinc-200 placeholder-zinc-500 outline-none" />
        <textarea value={html} onChange={(e) => setHtml(e.target.value)} placeholder="Paste sanitized HTML or leave blank for an empty starter" rows={5} className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-900 text-xs font-mono text-zinc-200 placeholder-zinc-500 outline-none" />
        <button onClick={save} disabled={!name.trim()} className="w-full px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded-lg disabled:opacity-40">Save template</button>
      </div>
    </div>
  )
}
