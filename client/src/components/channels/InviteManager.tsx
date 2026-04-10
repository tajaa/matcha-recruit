import { useState, useEffect } from 'react'
import { Link, Copy, Trash2, Plus, Check, Loader2 } from 'lucide-react'
import {
  listChannelInvites,
  createChannelInvite,
  revokeChannelInvite,
} from '../../api/channels'
import type { ChannelInvite } from '../../api/channels'

interface Props {
  channelId: string
  channelName: string
}

function relativeExpiry(iso: string): string {
  const diff = new Date(iso).getTime() - Date.now()
  if (diff <= 0) return 'Expired'
  const hours = Math.floor(diff / 3600000)
  if (hours < 24) return `${hours}h`
  const days = Math.floor(hours / 24)
  return `${days}d`
}

export default function InviteManager({ channelId }: Props) {
  const [invites, setInvites] = useState<ChannelInvite[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [creating, setCreating] = useState(false)
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [maxUses, setMaxUses] = useState<number | null>(null)
  const [expiresHours, setExpiresHours] = useState<number | null>(null)
  const [note, setNote] = useState('')

  useEffect(() => {
    listChannelInvites(channelId)
      .then(setInvites)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load invites'))
      .finally(() => setLoading(false))
  }, [channelId])

  const handleCreate = async () => {
    setCreating(true)
    setError('')
    try {
      const invite = await createChannelInvite(channelId, {
        max_uses: maxUses,
        expires_in_hours: expiresHours,
        note: note.trim() || null,
      })
      setInvites((prev) => [invite, ...prev])
      setShowForm(false)
      setMaxUses(null)
      setExpiresHours(null)
      setNote('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create invite')
    } finally {
      setCreating(false)
    }
  }

  const handleRevoke = async (inviteId: string) => {
    setError('')
    try {
      await revokeChannelInvite(channelId, inviteId)
      setInvites((prev) => prev.filter((i) => i.id !== inviteId))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to revoke invite')
    }
  }

  const handleCopy = (invite: ChannelInvite) => {
    navigator.clipboard.writeText(invite.url).then(() => {
      setCopiedId(invite.id)
      setTimeout(() => setCopiedId(null), 2000)
    })
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-4">
        <Loader2 className="w-4 h-4 text-zinc-500 animate-spin" />
      </div>
    )
  }

  const selectClass =
    'block w-full rounded-lg bg-zinc-800 border border-zinc-700 text-sm text-zinc-300 px-3 py-1.5 focus:outline-none focus:border-emerald-600'

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wider flex items-center gap-1.5">
          <Link className="w-3.5 h-3.5" />
          Invite Links
        </h3>
        {!showForm && (
          <button
            onClick={() => setShowForm(true)}
            className="flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300 transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            Create
          </button>
        )}
      </div>

      {error && (
        <p className="text-xs text-red-400 bg-red-900/20 rounded px-2 py-1">{error}</p>
      )}

      {showForm && (
        <div className="space-y-2 rounded-lg bg-zinc-800/50 p-3 border border-zinc-700">
          <label className="block">
            <span className="text-xs text-zinc-500">Max uses</span>
            <select
              value={maxUses ?? ''}
              onChange={(e) => setMaxUses(e.target.value ? Number(e.target.value) : null)}
              className={selectClass}
            >
              <option value="">Unlimited</option>
              <option value="1">1</option>
              <option value="5">5</option>
              <option value="10">10</option>
              <option value="25">25</option>
              <option value="50">50</option>
              <option value="100">100</option>
            </select>
          </label>
          <label className="block">
            <span className="text-xs text-zinc-500">Expires</span>
            <select
              value={expiresHours ?? ''}
              onChange={(e) => setExpiresHours(e.target.value ? Number(e.target.value) : null)}
              className={selectClass}
            >
              <option value="">Never</option>
              <option value="24">24 hours</option>
              <option value="48">48 hours</option>
              <option value="168">7 days</option>
              <option value="720">30 days</option>
            </select>
          </label>
          <label className="block">
            <span className="text-xs text-zinc-500">Note (optional)</span>
            <input
              type="text"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="e.g. For Twitter promo"
              className="mt-1 block w-full rounded-lg bg-zinc-800 border border-zinc-700 text-sm text-zinc-300 px-3 py-1.5 focus:outline-none focus:border-emerald-600 placeholder:text-zinc-600"
            />
          </label>
          <div className="flex gap-2 pt-1">
            <button
              onClick={handleCreate}
              disabled={creating}
              className="flex-1 flex items-center justify-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-50 transition-colors"
            >
              {creating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
              Generate
            </button>
            <button
              onClick={() => setShowForm(false)}
              className="text-xs text-zinc-500 hover:text-zinc-400 px-3 py-1.5 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {invites.length === 0 && !showForm && (
        <p className="text-xs text-zinc-600">No invite links yet.</p>
      )}

      <div className="space-y-1.5">
        {invites.map((inv) => (
          <div
            key={inv.id}
            className="flex items-center gap-2 px-2 py-1.5 rounded-lg bg-zinc-800/30 border border-zinc-800 group"
          >
            <div className="flex-1 min-w-0">
              <p className="text-xs text-zinc-400 truncate font-mono">{inv.url}</p>
              <div className="flex items-center gap-2 text-[11px] text-zinc-600">
                {inv.max_uses != null ? (
                  <span>{inv.use_count}/{inv.max_uses} uses</span>
                ) : (
                  <span>{inv.use_count} uses</span>
                )}
                <span>{inv.expires_at ? `Expires in ${relativeExpiry(inv.expires_at)}` : 'Never expires'}</span>
                {inv.note && <span className="truncate">{inv.note}</span>}
              </div>
            </div>
            <button
              onClick={() => handleCopy(inv)}
              className="shrink-0 p-1 text-zinc-500 hover:text-emerald-400 transition-colors"
              title="Copy link"
            >
              {copiedId === inv.id ? (
                <Check className="w-3.5 h-3.5 text-emerald-400" />
              ) : (
                <Copy className="w-3.5 h-3.5" />
              )}
            </button>
            <button
              onClick={() => handleRevoke(inv.id)}
              className="shrink-0 p-1 text-zinc-500 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100"
              title="Revoke"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
