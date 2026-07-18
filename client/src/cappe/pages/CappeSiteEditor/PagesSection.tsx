import { Link } from 'react-router-dom'
import { Loader2, Plus, Trash2, Pencil, Sparkles } from 'lucide-react'
import { PAGE_PRESETS, type CappePagePreset } from '../../data/cappePagePresets'
import type { CappePage } from '../../types'
import { statusStyle } from './styles'

export function PagesSection({
  siteId, pages, newPageTitle, setNewPageTitle, addingPage,
  onAddPage, onAddPreset, onDeletePage,
}: {
  siteId: string
  pages: CappePage[]
  newPageTitle: string
  setNewPageTitle: (v: string) => void
  addingPage: boolean
  onAddPage: (e: React.FormEvent) => void
  onAddPreset: (p: CappePagePreset) => void
  onDeletePage: (pageId: string) => void
}) {
  return (
    <section className="mb-6 rounded-2xl border border-zinc-800 bg-zinc-900 p-6">
      <h2 className="mb-4 text-sm font-semibold text-zinc-100">Pages</h2>
      <ul className="mb-4 divide-y divide-zinc-800">
        {pages.length === 0 && <li className="py-3 text-sm text-zinc-500">No pages yet.</li>}
        {pages.map((p) => (
          <li key={p.id} className="flex items-center justify-between py-3">
            <Link to={`/cappe/sites/${siteId}/pages/${p.id}`} className="group flex-1">
              <div className="text-sm font-medium text-zinc-200 group-hover:text-emerald-400">{p.title}</div>
              <div className="text-xs text-zinc-500">/{p.slug}</div>
            </Link>
            <div className="flex items-center gap-3">
              <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${statusStyle[p.status] || statusStyle.draft}`}>
                {p.status}
              </span>
              <Link
                to={`/cappe/sites/${siteId}/pages/${p.id}`}
                className="inline-flex items-center gap-1 rounded-md border border-zinc-700 px-2.5 py-1 text-xs font-medium text-zinc-300 hover:bg-zinc-800"
              >
                <Pencil className="h-3.5 w-3.5" /> Edit
              </Link>
              <button onClick={() => onDeletePage(p.id)} className="text-zinc-500 hover:text-red-400">
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          </li>
        ))}
      </ul>
      <form onSubmit={onAddPage} className="flex gap-2">
        <input
          value={newPageTitle}
          onChange={(e) => setNewPageTitle(e.target.value)}
          placeholder="New page title"
          className="flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
        />
        <button
          type="submit"
          disabled={addingPage || !newPageTitle.trim()}
          className="flex items-center gap-2 rounded-lg bg-emerald-500 px-3 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-60"
        >
          {addingPage ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
          Add
        </button>
      </form>

      {/* One-click page presets — seed a ready-made, fully-editable page. */}
      <div className="mt-4 border-t border-zinc-800 pt-4">
        <p className="mb-2 text-xs font-medium text-zinc-400">Or start from a template</p>
        <div className="grid gap-2 sm:grid-cols-2">
          {PAGE_PRESETS.map((p) => (
            <button
              key={p.id}
              onClick={() => onAddPreset(p)}
              disabled={addingPage}
              className="flex flex-col items-start rounded-lg border border-zinc-800 bg-zinc-950/60 px-3 py-2.5 text-left hover:border-emerald-500/60 hover:bg-zinc-900 disabled:opacity-60"
            >
              <span className="flex items-center gap-1.5 text-sm font-semibold text-zinc-200">
                <Sparkles className="h-3.5 w-3.5 text-emerald-400" /> {p.label}
              </span>
              <span className="mt-0.5 text-xs text-zinc-500">{p.blurb}</span>
            </button>
          ))}
        </div>
      </div>
    </section>
  )
}
