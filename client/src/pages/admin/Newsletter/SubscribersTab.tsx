import { Search, Upload, Tag as TagIcon, Trash2 } from 'lucide-react'
import type { Subscriber, Tag } from './types'

export function SubscribersTab({
  search, onSearchChange,
  filteredSubs,
  tags,
  subTagsCache,
  managingTagsFor, onManagingTagsForChange,
  onImportOpen,
  onExport,
  onLoadSubTags,
  onToggleSubTag,
  onDeleteSubscriber,
}: {
  search: string; onSearchChange: (v: string) => void
  filteredSubs: Subscriber[]
  tags: Tag[]
  subTagsCache: Record<string, Tag[]>
  managingTagsFor: string | null; onManagingTagsForChange: (id: string | null) => void
  onImportOpen: () => void
  onExport: () => void
  onLoadSubTags: (subscriberId: string) => Promise<void>
  onToggleSubTag: (subscriberId: string, tagId: string) => Promise<void>
  onDeleteSubscriber: (id: string, email: string) => Promise<void>
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-4 gap-3">
        <div className="relative max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input value={search} onChange={(e) => onSearchChange(e.target.value)} placeholder="Search..." className="w-full pl-9 pr-3 py-2 rounded-lg border border-slate-300 bg-white text-sm text-slate-900 placeholder-slate-400 outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 transition-colors" />
        </div>
        <div className="flex gap-2">
          <button onClick={onImportOpen} className="px-3 py-1.5 text-xs text-slate-700 bg-white hover:bg-slate-50 border border-slate-300 rounded-lg shadow-sm flex items-center gap-1">
            <Upload size={12} /> Import CSV
          </button>
          <button onClick={onExport} className="px-3 py-1.5 text-xs text-slate-700 bg-white hover:bg-slate-50 border border-slate-300 rounded-lg shadow-sm">Export CSV</button>
        </div>
      </div>
      {managingTagsFor && (
        <div className="fixed inset-0 z-40" onClick={() => onManagingTagsForChange(null)} />
      )}
      <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-200">
              <th className="text-left px-4 py-2.5 text-slate-500 font-medium uppercase tracking-wide text-[10px]">Email</th>
              <th className="text-left px-4 py-2.5 text-slate-500 font-medium uppercase tracking-wide text-[10px]">Name</th>
              <th className="text-left px-4 py-2.5 text-slate-500 font-medium uppercase tracking-wide text-[10px]">Source</th>
              <th className="text-left px-4 py-2.5 text-slate-500 font-medium uppercase tracking-wide text-[10px]">Status</th>
              <th className="text-left px-4 py-2.5 text-slate-500 font-medium uppercase tracking-wide text-[10px]">Groups</th>
              <th className="text-left px-4 py-2.5 text-slate-500 font-medium uppercase tracking-wide text-[10px]">Subscribed</th>
              <th className="px-4 py-2.5"></th>
            </tr>
          </thead>
          <tbody>
            {filteredSubs.map((s) => (
              <tr key={s.id} className="border-b border-slate-100 hover:bg-slate-50">
                <td className="px-4 py-2.5 text-slate-800">{s.email}</td>
                <td className="px-4 py-2.5 text-slate-500">{s.name || '--'}</td>
                <td className="px-4 py-2.5"><span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-100 text-slate-500">{s.source}</span></td>
                <td className="px-4 py-2.5">
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                    s.status === 'active' ? 'bg-emerald-50 text-emerald-700'
                    : s.status === 'pending' ? 'bg-amber-50 text-amber-700'
                    : s.status === 'bounced' ? 'bg-red-50 text-red-700'
                    : 'bg-slate-100 text-slate-500'
                  }`}>{s.status}</span>
                </td>
                <td className="px-4 py-2.5 relative">
                  <div className="flex items-center gap-1 flex-wrap">
                    {(subTagsCache[s.id] ?? []).map(t => (
                      <span key={t.id} className="px-1.5 py-0.5 rounded text-[10px] bg-slate-100 text-slate-600">{t.label}</span>
                    ))}
                    <button
                      onClick={async (e) => { e.stopPropagation(); await onLoadSubTags(s.id); onManagingTagsForChange(managingTagsFor === s.id ? null : s.id) }}
                      className="text-slate-400 hover:text-emerald-600 transition-colors"
                      title="Manage groups"
                    ><TagIcon size={11} /></button>
                  </div>
                  {managingTagsFor === s.id && (
                    <div className="absolute left-0 top-full mt-1 z-50 bg-white border border-slate-200 rounded-lg p-2 shadow-lg min-w-[180px]" onClick={e => e.stopPropagation()}>
                      {tags.length === 0
                        ? <p className="text-[10px] text-slate-400 px-1 py-0.5">No groups yet. Create one in the Groups tab.</p>
                        : tags.map(t => (
                          <label key={t.id} className="flex items-center gap-2 px-1 py-1 text-[11px] text-slate-600 cursor-pointer hover:text-slate-900">
                            <input
                              type="checkbox"
                              className="accent-emerald-600"
                              checked={(subTagsCache[s.id] ?? []).some(st => st.id === t.id)}
                              onChange={() => onToggleSubTag(s.id, t.id)}
                            />
                            {t.label}
                          </label>
                        ))
                      }
                      <button onClick={() => onManagingTagsForChange(null)} className="mt-1 w-full text-[10px] text-slate-400 hover:text-slate-700 text-right pr-1">Done</button>
                    </div>
                  )}
                </td>
                <td className="px-4 py-2.5 text-slate-400">{new Date(s.subscribed_at).toLocaleDateString()}</td>
                <td className="px-4 py-2.5 text-right">
                  <button
                    onClick={() => onDeleteSubscriber(s.id, s.email)}
                    className="text-slate-400 hover:text-red-600"
                    title="Delete (GDPR erasure)"
                  ><Trash2 size={13} /></button>
                </td>
              </tr>
            ))}
            {filteredSubs.length === 0 && (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-400">No subscribers yet</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
