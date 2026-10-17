import { AdminInput, AdminButton, AdminTable } from '../../../../components/admin/AdminUI'
import React, { useState } from 'react'
import { Trash2, X, ChevronDown, UserPlus, Loader2 } from 'lucide-react'
import { api } from '../../../../api/client'
import type { Tag, Subscriber } from './types'

export function TagsTab({ tags, onChange, subscribers }: {
  tags: Tag[]
  onChange: () => Promise<void> | void
  subscribers: Subscriber[]
}) {
  const [slug, setSlug] = useState('')
  const [label, setLabel] = useState('')
  const [desc, setDesc] = useState('')
  const [expandedTag, setExpandedTag] = useState<string | null>(null)
  const [tagMembers, setTagMembers] = useState<Record<string, { id: string; email: string; name: string | null; status: string }[]>>({})
  const [loadingMembers, setLoadingMembers] = useState<Set<string>>(new Set())
  const [addSearch, setAddSearch] = useState<Record<string, string>>({})

  async function add() {
    if (!slug.trim() || !label.trim()) return
    await api.post('/admin/newsletter/tags', { slug: slug.trim(), label: label.trim(), description: desc.trim() || undefined })
    setSlug(''); setLabel(''); setDesc('')
    await onChange()
  }

  async function remove(id: string) {
    if (!confirm('Delete this tag? Subscribers tagged with it lose the assignment.')) return
    await api.delete(`/admin/newsletter/tags/${id}`)
    if (expandedTag === id) setExpandedTag(null)
    await onChange()
  }

  async function expandTag(tagId: string) {
    if (expandedTag === tagId) { setExpandedTag(null); return }
    setExpandedTag(tagId)
    if (tagMembers[tagId] === undefined) {
      setLoadingMembers(prev => new Set(prev).add(tagId))
      try {
        const res = await api.get<{ subscribers: { id: string; email: string; name: string | null; status: string }[] }>(`/admin/newsletter/tags/${tagId}/subscribers`)
        setTagMembers(prev => ({ ...prev, [tagId]: res.subscribers }))
      } catch {
        setTagMembers(prev => ({ ...prev, [tagId]: [] }))
      } finally {
        setLoadingMembers(prev => { const s = new Set(prev); s.delete(tagId); return s })
      }
    }
  }

  async function removeMemberFromTag(tagId: string, subscriberId: string) {
    try {
      const res = await api.get<{ tags: Tag[] }>(`/admin/newsletter/subscribers/${subscriberId}/tags`)
      const next = res.tags.filter(t => t.id !== tagId).map(t => t.id)
      await api.put(`/admin/newsletter/subscribers/${subscriberId}/tags`, { tag_ids: next })
      setTagMembers(prev => ({ ...prev, [tagId]: (prev[tagId] ?? []).filter(m => m.id !== subscriberId) }))
      await onChange()
    } catch { /* Preserve the existing best-effort fallback. */ }
  }

  async function addMemberToTag(tagId: string, sub: Subscriber) {
    try {
      const res = await api.get<{ tags: Tag[] }>(`/admin/newsletter/subscribers/${sub.id}/tags`)
      const alreadyIn = res.tags.some(t => t.id === tagId)
      if (alreadyIn) return
      await api.put(`/admin/newsletter/subscribers/${sub.id}/tags`, { tag_ids: [...res.tags.map(t => t.id), tagId] })
      setTagMembers(prev => ({ ...prev, [tagId]: [...(prev[tagId] ?? []), { id: sub.id, email: sub.email, name: sub.name, status: sub.status }] }))
      setAddSearch(prev => ({ ...prev, [tagId]: '' }))
      await onChange()
    } catch { /* Preserve the existing best-effort fallback. */ }
  }

  return (
    <div className="space-y-4 max-w-2xl">
      <div className="rounded-xl border border-zinc-800 p-4">
        <p className="text-xs text-zinc-400 mb-3">Add a tag (slug must be lowercase, no spaces).</p>
        <div className="grid grid-cols-3 gap-2 mb-2">
          <AdminInput value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="slug (e.g. hospitality)"  />
          <AdminInput value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Label (e.g. Hospitality)"  />
          <AdminButton onClick={add} disabled={!slug.trim() || !label.trim()} className="disabled:opacity-40" variant="success">Add tag</AdminButton>
        </div>
        <AdminInput value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Description (optional)"  />
      </div>
      <AdminTable>
        <thead className="border-b border-zinc-800">
          <tr>
            <th className="text-left text-zinc-400">Slug</th>
            <th className="text-left text-zinc-400">Label</th>
            <th className="text-left text-zinc-400">Description</th>
            <th className="text-right text-zinc-400">Subs</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {tags.map((t) => {
            const members = tagMembers[t.id] ?? []
            const search = addSearch[t.id] ?? ''
            const searchResults = search.length >= 1
              ? subscribers.filter(s =>
                  !members.some(m => m.id === s.id) &&
                  (s.email.toLowerCase().includes(search.toLowerCase()) || (s.name || '').toLowerCase().includes(search.toLowerCase()))
                ).slice(0, 6)
              : []
            return (
              <React.Fragment key={t.id}>
                <tr
                  className="border-b border-zinc-800/50 hover:bg-zinc-800/20 cursor-pointer"
                  onClick={() => expandTag(t.id)}
                >
                  <td className="font-mono text-zinc-300">{t.slug}</td>
                  <td className="text-zinc-200">{t.label}</td>
                  <td className="text-zinc-500">{t.description ?? '—'}</td>
                  <td className="text-right text-zinc-400">{t.subscriber_count}</td>
                  <td className="text-right">
                    <div className="flex items-center gap-2 justify-end">
                      <ChevronDown
                        size={12}
                        className={`text-zinc-500 transition-transform ${expandedTag === t.id ? 'rotate-180' : ''}`}
                      />
                      <button
                        onClick={(e) => { e.stopPropagation(); remove(t.id) }}
                        className="text-zinc-500 hover:text-red-400"
                        title="Delete tag"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </td>
                </tr>
                {expandedTag === t.id && (
                  <tr>
                    <td colSpan={5} className="border-b">
                      {loadingMembers.has(t.id) && (
                        <p className="text-[11px] text-zinc-500 mb-2 flex items-center gap-1"><Loader2 size={10} className="animate-spin" /> Loading…</p>
                      )}
                      {!loadingMembers.has(t.id) && tagMembers[t.id] !== undefined && members.length === 0 && (
                        <p className="text-[11px] text-zinc-500 mb-2">No members yet.</p>
                      )}
                      {members.length > 0 && (
                        <div className="space-y-1 mb-3">
                          {members.map(m => (
                            <div key={m.id} className="flex items-center gap-2">
                              <span className="text-[11px] text-zinc-300 flex-1">{m.email}</span>
                              <span className={`px-1.5 py-0.5 rounded text-[10px] ${
                                m.status === 'active' ? 'bg-emerald-900/30 text-emerald-400'
                                : m.status === 'pending' ? 'bg-amber-900/30 text-amber-400'
                                : 'bg-zinc-800 text-zinc-500'
                              }`}>{m.status}</span>
                              <button
                                onClick={() => removeMemberFromTag(t.id, m.id)}
                                className="text-zinc-600 hover:text-red-400"
                                title="Remove from group"
                              >
                                <X size={11} />
                              </button>
                            </div>
                          ))}
                        </div>
                      )}
                      {/* Add subscriber search */}
                      <div className="relative">
                        <div className="flex items-center gap-2">
                          <UserPlus size={11} className="text-zinc-500 shrink-0" />
                          <AdminInput
                            value={search}
                            onChange={(e) => setAddSearch(prev => ({ ...prev, [t.id]: e.target.value }))}
                            placeholder="Add subscriber by email…"
                            className="flex-1"
                            onClick={(e) => e.stopPropagation()}
                          />
                        </div>
                        {searchResults.length > 0 && (
                          <div className="absolute left-6 top-full mt-1 z-50 bg-zinc-900 border border-zinc-700 rounded-lg shadow-xl w-72">
                            {searchResults.map(s => (
                              <button
                                key={s.id}
                                onClick={(e) => { e.stopPropagation(); addMemberToTag(t.id, s) }}
                                className="w-full text-left px-3 py-2 text-[11px] text-zinc-300 hover:bg-zinc-800 flex items-center gap-2"
                              >
                                <span className="flex-1 truncate">{s.email}</span>
                                {s.name && <span className="text-zinc-500 truncate max-w-[100px]">{s.name}</span>}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            )
          })}
          {tags.length === 0 && <tr><td colSpan={5} className="text-center text-zinc-500">No tags yet.</td></tr>}
        </tbody>
      </AdminTable>
    </div>
  )
}
