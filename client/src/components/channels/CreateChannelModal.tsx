import { useState } from 'react'
import { X, Loader2, Hash, Globe, Lock, UserPlus } from 'lucide-react'
import { createChannel } from '../../api/channels'

interface Props {
  onClose: () => void
  onCreated: (channel: { id: string; name: string; slug: string }) => void
}

export default function CreateChannelModal({ onClose, onCreated }: Props) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [visibility, setVisibility] = useState<'public' | 'invite_only' | 'private'>('public')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    setCreating(true)
    setError('')
    try {
      const ch = await createChannel(name.trim(), description.trim() || undefined, visibility)
      onCreated(ch)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create channel')
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 w-full max-w-sm mx-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Hash size={18} className="text-emerald-500" />
            <h2 className="text-white font-semibold">New Channel</h2>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-white">
            <X size={16} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-xs text-zinc-400 mb-1">Channel name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. hr-ops, general"
              maxLength={100}
              autoFocus
              className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm placeholder:text-zinc-500 focus:outline-none focus:border-emerald-600"
            />
          </div>
          <div>
            <label className="block text-xs text-zinc-400 mb-1">Description (optional)</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What's this channel for?"
              rows={2}
              className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm placeholder:text-zinc-500 focus:outline-none focus:border-emerald-600 resize-none"
            />
          </div>
          <div>
            <label className="block text-xs text-zinc-400 mb-1.5">Visibility</label>
            <div className="flex gap-2">
              {([
                { value: 'public' as const, icon: Globe, label: 'Public', desc: 'Anyone can join' },
                { value: 'invite_only' as const, icon: UserPlus, label: 'Invite Only', desc: 'Visible, but must be invited' },
                { value: 'private' as const, icon: Lock, label: 'Private', desc: 'Hidden from non-members' },
              ]).map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setVisibility(opt.value)}
                  className={`flex-1 flex flex-col items-center gap-1 px-2 py-2 rounded-lg border text-[11px] transition-colors ${
                    visibility === opt.value
                      ? 'border-emerald-600 bg-emerald-600/10 text-emerald-400'
                      : 'border-zinc-700 bg-zinc-800 text-zinc-400 hover:border-zinc-600'
                  }`}
                >
                  <opt.icon size={14} />
                  <span className="font-medium">{opt.label}</span>
                </button>
              ))}
            </div>
          </div>
          {error && <p className="text-red-400 text-xs">{error}</p>}
          <button
            type="submit"
            disabled={creating || !name.trim()}
            className="w-full py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
          >
            {creating ? <Loader2 size={16} className="animate-spin mx-auto" /> : 'Create Channel'}
          </button>
        </form>
      </div>
    </div>
  )
}
