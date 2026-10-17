import { AdminInput, AdminButton, AdminTable } from '../../../../components/admin/AdminUI'
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
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
          <AdminInput value={search} onChange={(e) => onSearchChange(e.target.value)} placeholder="Search..." className="pl-9 pr-3" />
        </div>
        <div className="flex gap-2">
          <AdminButton onClick={onImportOpen} className="gap-1" variant="secondary">
            <Upload size={12} /> Import CSV
          </AdminButton>
          <AdminButton onClick={onExport}  variant="secondary">Export CSV</AdminButton>
        </div>
      </div>
      {managingTagsFor && (
        <div className="fixed inset-0 z-40" onClick={() => onManagingTagsForChange(null)} />
      )}
      <AdminTable>
        <thead>
          <tr className="bg-zinc-900/80 border-b border-zinc-800">
            <th className="text-left text-zinc-400">Email</th>
            <th className="text-left text-zinc-400">Name</th>
            <th className="text-left text-zinc-400">Source</th>
            <th className="text-left text-zinc-400">Status</th>
            <th className="text-left text-zinc-400">Groups</th>
            <th className="text-left text-zinc-400">Subscribed</th>
            <th ></th>
          </tr>
        </thead>
        <tbody>
          {filteredSubs.map((s) => (
            <tr key={s.id} className="border-b border-zinc-800/50 hover:bg-zinc-800/20">
              <td className="text-zinc-200">{s.email}</td>
              <td className="text-zinc-400">{s.name || '--'}</td>
              <td ><span className="px-1.5 py-0.5 rounded text-[10px] bg-zinc-800 text-zinc-400">{s.source}</span></td>
              <td >
                <span className={`px-1.5 py-0.5 rounded text-[10px] ${
                  s.status === 'active' ? 'bg-emerald-900/30 text-emerald-400'
                  : s.status === 'pending' ? 'bg-amber-900/30 text-amber-400'
                  : s.status === 'bounced' ? 'bg-red-900/30 text-red-400'
                  : 'bg-zinc-800 text-zinc-500'
                }`}>{s.status}</span>
              </td>
              <td className="relative">
                <div className="flex items-center gap-1 flex-wrap">
                  {(subTagsCache[s.id] ?? []).map(t => (
                    <span key={t.id} className="px-1.5 py-0.5 rounded text-[10px] bg-zinc-700 text-zinc-300">{t.label}</span>
                  ))}
                  <button
                    onClick={async (e) => { e.stopPropagation(); await onLoadSubTags(s.id); onManagingTagsForChange(managingTagsFor === s.id ? null : s.id) }}
                    className="text-zinc-500 hover:text-emerald-400 transition-colors"
                    title="Manage groups"
                  ><TagIcon size={11} /></button>
                </div>
                {managingTagsFor === s.id && (
                  <div className="absolute left-0 top-full mt-1 z-50 bg-zinc-900 border border-zinc-700 rounded-lg p-2 shadow-xl min-w-[180px]" onClick={e => e.stopPropagation()}>
                    {tags.length === 0
                      ? <p className="text-[10px] text-zinc-500 px-1 py-0.5">No groups yet. Create one in the Groups tab.</p>
                      : tags.map(t => (
                        <label key={t.id} className="flex items-center gap-2 px-1 py-1 text-[11px] text-zinc-300 cursor-pointer hover:text-zinc-100">
                          <input
                            type="checkbox"
                            className="accent-emerald-500"
                            checked={(subTagsCache[s.id] ?? []).some(st => st.id === t.id)}
                            onChange={() => onToggleSubTag(s.id, t.id)}
                          />
                          {t.label}
                        </label>
                      ))
                    }
                    <button onClick={() => onManagingTagsForChange(null)} className="mt-1 w-full text-[10px] text-zinc-500 hover:text-zinc-300 text-right pr-1">Done</button>
                  </div>
                )}
              </td>
              <td className="text-zinc-500">{new Date(s.subscribed_at).toLocaleDateString()}</td>
              <td className="text-right">
                <button
                  onClick={() => onDeleteSubscriber(s.id, s.email)}
                  className="text-zinc-500 hover:text-red-400"
                  title="Delete (GDPR erasure)"
                ><Trash2 size={13} /></button>
              </td>
            </tr>
          ))}
          {filteredSubs.length === 0 && (
            <tr><td colSpan={7} className="text-center text-zinc-500">No subscribers yet</td></tr>
          )}
        </tbody>
      </AdminTable>
    </div>
  )
}
