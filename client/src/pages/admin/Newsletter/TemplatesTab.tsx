import { useState } from 'react'
import { Layout, Trash2, Sparkles, Wand2 } from 'lucide-react'
import { api } from '../../../api/client'
import type { Template } from './types'
import type { NewsletterDesign } from './blocks/schema'
import { designHasMedia } from './blocks/schema'
import { STARTERS, instantiateStarter } from './blocks/starterTemplates'

export function TemplatesTab({
  templates,
  onChange,
  onPickTemplate,
  onStartFrom,
  currentDesign,
}: {
  templates: Template[]
  onChange: () => Promise<void> | void
  onPickTemplate: (t: Template) => Promise<void> | void
  onStartFrom: (design: NewsletterDesign, name: string) => void
  currentDesign: NewsletterDesign | null
}) {
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [pre, setPre] = useState('')
  const [html, setHtml] = useState('')
  const [saving, setSaving] = useState(false)

  async function save() {
    if (!name.trim()) return
    await api.post('/admin/newsletter/templates', {
      name: name.trim(), description: desc || undefined,
      content_html: html || undefined, preheader: pre || undefined,
    })
    setName(''); setDesc(''); setPre(''); setHtml('')
    await onChange()
  }

  async function saveCurrentDesign() {
    const tplName = window.prompt('Name this template:', currentDesign ? '' : '')
    if (!tplName || !tplName.trim()) return
    setSaving(true)
    try {
      await api.post('/admin/newsletter/templates', {
        name: tplName.trim(),
        design_json: currentDesign,
      })
      await onChange()
    } catch (err) {
      alert(`Could not save template: ${(err as Error).message}`)
    }
    setSaving(false)
  }

  async function remove(id: string) {
    if (!confirm('Delete template? Existing newsletters built from it are unaffected.')) return
    await api.delete(`/admin/newsletter/templates/${id}`)
    await onChange()
  }

  const currentHasBlocks = !!currentDesign?.blocks?.length

  return (
    <div className="space-y-8 max-w-6xl">
      {/* Starter templates — designed scaffolds to begin from */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <Sparkles size={14} className="text-emerald-400" />
          <h3 className="text-sm font-medium text-zinc-200">Start from a designed template</h3>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {STARTERS.map((s) => (
            <button
              key={s.key}
              onClick={() => onStartFrom(instantiateStarter(s), s.name)}
              className="text-left rounded-xl border border-zinc-800 hover:border-emerald-600/50 bg-zinc-900/40 p-4 transition-colors group"
            >
              <div className="flex items-center gap-2 mb-1.5">
                <Wand2 size={13} className="text-zinc-500 group-hover:text-emerald-400" />
                <span className="text-sm font-medium text-zinc-200">{s.name}</span>
              </div>
              <p className="text-[11px] text-zinc-500 leading-snug">{s.description}</p>
              <span className="inline-block mt-2 text-[11px] text-emerald-400">Use this →</span>
            </button>
          ))}
        </div>
      </div>

      {/* Saved templates */}
      <div className="grid lg:grid-cols-[1fr_360px] gap-6">
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-xs text-zinc-400">Your saved templates seed new newsletters with proven content.</p>
            {currentHasBlocks && (
              <button
                onClick={saveCurrentDesign}
                disabled={saving}
                className="text-[11px] px-2.5 py-1 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 disabled:opacity-40"
              >
                Save current design
              </button>
            )}
          </div>
          {templates.length === 0 && <p className="text-zinc-500 text-sm py-4">No saved templates yet.</p>}
          {templates.map((t) => (
            <div key={t.id} className="rounded-xl border border-zinc-800 px-4 py-3 flex items-center gap-3">
              <Layout size={14} className="text-zinc-500 shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-sm text-zinc-200 truncate">{t.name}</p>
                  {t.design_json && (
                    <span className="text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-400">Design</span>
                  )}
                </div>
                {t.description && <p className="text-[11px] text-zinc-500 truncate">{t.description}</p>}
              </div>
              <button onClick={() => onPickTemplate(t)} className="text-xs text-emerald-400 hover:text-emerald-300">Use →</button>
              <button onClick={() => remove(t.id)} className="text-zinc-500 hover:text-red-400"><Trash2 size={13} /></button>
            </div>
          ))}
        </div>
        <div className="rounded-xl border border-zinc-800 p-4 space-y-3 self-start">
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider">Save a raw-HTML template</p>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Template name" className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-900 text-sm text-zinc-200 placeholder-zinc-500 outline-none" />
          <input value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Description (optional)" className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-900 text-sm text-zinc-200 placeholder-zinc-500 outline-none" />
          <input value={pre} onChange={(e) => setPre(e.target.value)} placeholder="Preheader (optional)" className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-900 text-sm text-zinc-200 placeholder-zinc-500 outline-none" />
          <textarea value={html} onChange={(e) => setHtml(e.target.value)} placeholder="Paste sanitized HTML or leave blank for an empty starter" rows={5} className="w-full px-3 py-2 rounded-lg border border-zinc-700 bg-zinc-900 text-xs font-mono text-zinc-200 placeholder-zinc-500 outline-none" />
          <button onClick={save} disabled={!name.trim()} className="w-full px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded-lg disabled:opacity-40">Save template</button>
        </div>
      </div>
    </div>
  )
}
