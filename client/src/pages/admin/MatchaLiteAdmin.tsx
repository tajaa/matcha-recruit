import { useState, useEffect } from 'react'
import { Copy, Check, Link, Trash2 } from 'lucide-react'
import { api } from '../../api/client'
import MatchaLitePricingPanel from './MatchaLitePricingPanel'

type InviteToken = {
  id: string
  token: string
  note: string | null
  signup_url: string
  signup_url_x: string
  signup_url_compliance: string
  created_at: string
  used_at: string | null
  company_name: string | null
}

export default function MatchaLiteAdmin() {
  const [tab, setTab] = useState<'links' | 'pricing' | 'bespoke'>('links')
  const [tokens, setTokens] = useState<InviteToken[]>([])
  const [note, setNote] = useState('')
  const [generating, setGenerating] = useState(false)
  const [newToken, setNewToken] = useState<InviteToken | null>(null)
  // Tracks which exact URL was last copied so the right button shows the check.
  const [copied, setCopied] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function load() {
    const data = await api.get<InviteToken[]>('/admin/matcha-lite/invite-tokens')
    setTokens(data)
  }

  useEffect(() => { load() }, [])

  async function generate() {
    setGenerating(true)
    setError(null)
    setNewToken(null)
    try {
      const res = await api.post<InviteToken>('/admin/matcha-lite/invite-tokens', { note: note.trim() || null })
      setNewToken(res)
      setNote('')
      await load()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to generate link')
    } finally {
      setGenerating(false)
    }
  }

  function copyUrl(url: string) {
    navigator.clipboard.writeText(url)
    setCopied(url)
    setTimeout(() => setCopied((c) => (c === url ? null : c)), 2000)
  }

  async function deleteToken(id: string) {
    if (!confirm('Delete this unused signup link?')) return
    await api.delete(`/admin/matcha-lite/invite-tokens/${id}`)
    await load()
  }

  return (
    <div className="p-6 max-w-3xl">
      <h1 className="text-xl font-semibold text-zinc-100 mb-1">Self-Serve Signup Links</h1>
      <p className="text-sm text-zinc-500 mb-6">Comp signup links and pricing for Lite, Matcha-X, and Compliance.</p>

      <div className="flex gap-1 mb-6 border-b border-zinc-800">
        <button
          onClick={() => setTab('links')}
          className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
            tab === 'links' ? 'text-zinc-100 border-emerald-600' : 'text-zinc-500 border-transparent hover:text-zinc-300'
          }`}
        >
          Comp Signup Links
        </button>
        <button
          onClick={() => setTab('pricing')}
          className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
            tab === 'pricing' ? 'text-zinc-100 border-emerald-600' : 'text-zinc-500 border-transparent hover:text-zinc-300'
          }`}
        >
          Pricing
        </button>
        <button
          onClick={() => setTab('bespoke')}
          className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
            tab === 'bespoke' ? 'text-zinc-100 border-emerald-600' : 'text-zinc-500 border-transparent hover:text-zinc-300'
          }`}
        >
          Bespoke / Pro Invites
        </button>
      </div>

      {tab === 'pricing' && <MatchaLitePricingPanel />}
      {tab === 'bespoke' && <BespokeInvitesPanel />}

      {tab !== 'links' ? null : <>
      <p className="text-sm text-zinc-500 mb-6">
        One-use links that activate an account instantly with <span className="text-zinc-300 font-medium">no Stripe charge</span> —
        the comped/invoiced path. Each token works for any tier; send the <span className="text-emerald-300">Lite</span>,{' '}
        <span className="text-teal-300">Matcha-X</span>, or <span className="text-amber-300">Compliance</span> link depending on what
        you're comping. For a paying self-serve customer, send the plain public signup URL instead (e.g. <code className="text-zinc-400">/compliance/signup</code>) —
        that one still requires Stripe checkout.
      </p>

      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 mb-6">
        <h2 className="text-sm font-medium text-zinc-300 mb-3">Generate signup link</h2>
        <div className="flex gap-2">
          <input
            type="text"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Note (e.g. customer name)"
            className="flex-1 bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-emerald-700"
          />
          <button
            onClick={generate}
            disabled={generating}
            className="px-4 py-2 bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white text-sm font-medium rounded transition-colors flex items-center gap-2"
          >
            <Link className="w-4 h-4" />
            Generate
          </button>
        </div>
        {error && <p className="mt-2 text-sm text-red-400">{error}</p>}
        {newToken && (
          <div className="mt-3 space-y-2">
            <LinkRow label="Lite" url={newToken.signup_url} copied={copied} onCopy={copyUrl} />
            <LinkRow label="Matcha-X" url={newToken.signup_url_x} copied={copied} onCopy={copyUrl} />
            <LinkRow label="Compliance" url={newToken.signup_url_compliance} copied={copied} onCopy={copyUrl} />
          </div>
        )}
      </div>

      <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-800">
              <th className="text-left px-4 py-3 text-xs text-zinc-500 uppercase tracking-wide font-medium">Note</th>
              <th className="text-left px-4 py-3 text-xs text-zinc-500 uppercase tracking-wide font-medium">Created</th>
              <th className="text-left px-4 py-3 text-xs text-zinc-500 uppercase tracking-wide font-medium">Status</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {tokens.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-zinc-500 text-sm">No links generated yet</td>
              </tr>
            )}
            {tokens.map((t) => (
              <tr key={t.id} className="border-b border-zinc-800 last:border-0">
                <td className="px-4 py-3 text-zinc-300">{t.note ?? <span className="text-zinc-600">—</span>}</td>
                <td className="px-4 py-3 text-zinc-400">{new Date(t.created_at).toLocaleDateString()}</td>
                <td className="px-4 py-3">
                  {t.used_at ? (
                    <span className="text-zinc-500 text-xs">
                      Used by {t.company_name ?? 'unknown'} · {new Date(t.used_at).toLocaleDateString()}
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-xs text-emerald-400 bg-emerald-950 px-2 py-0.5 rounded-full">
                      Available
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 text-right">
                  {!t.used_at && (
                    <div className="flex items-center justify-end gap-2">
                      <CopyChip label="Lite" url={t.signup_url} copied={copied} onCopy={copyUrl} />
                      <CopyChip label="X" url={t.signup_url_x} copied={copied} onCopy={copyUrl} />
                      <CopyChip label="Compliance" url={t.signup_url_compliance} copied={copied} onCopy={copyUrl} />
                      <button
                        onClick={() => deleteToken(t.id)}
                        className="text-zinc-600 hover:text-red-400 transition-colors"
                        title="Delete link"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      </>}
    </div>
  )
}

type BusinessInvite = {
  id: string
  token: string
  invite_url: string
  status: string
  note: string | null
  created_by_email: string
  used_by_company_name: string | null
  expires_at: string
  used_at: string | null
  created_at: string
}

// Generic, tier-agnostic invite: redeeming it (/register/invite/:token, via
// BusinessInviteRegister.tsx) provisions a full Pro/bespoke company with no
// Stripe checkout — the same "no payment, comped/invoiced" model as the
// Lite/X/Compliance tokens above, but for the full platform tier.
function BespokeInvitesPanel() {
  const [invites, setInvites] = useState<BusinessInvite[]>([])
  const [note, setNote] = useState('')
  const [expiresDays, setExpiresDays] = useState('7')
  const [generating, setGenerating] = useState(false)
  const [newInvite, setNewInvite] = useState<BusinessInvite | null>(null)
  const [copied, setCopied] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function load() {
    const data = await api.get<{ invites: BusinessInvite[]; total: number }>('/admin/business-invites')
    setInvites(data.invites)
  }

  useEffect(() => { load() }, [])

  async function generate() {
    setGenerating(true)
    setError(null)
    setNewInvite(null)
    try {
      const days = parseInt(expiresDays, 10)
      const res = await api.post<BusinessInvite>('/admin/business-invites', {
        note: note.trim() || null,
        expires_days: !isNaN(days) && days >= 1 && days <= 90 ? days : 7,
      })
      setNewInvite(res)
      setNote('')
      await load()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to generate invite')
    } finally {
      setGenerating(false)
    }
  }

  function copyUrl(url: string) {
    navigator.clipboard.writeText(url)
    setCopied(url)
    setTimeout(() => setCopied((c) => (c === url ? null : c)), 2000)
  }

  async function cancelInvite(id: string) {
    if (!confirm('Cancel this pending invite?')) return
    await api.delete(`/admin/business-invites/${id}`)
    await load()
  }

  return (
    <>
      <p className="text-sm text-zinc-500 mb-6">
        Provisions a full Pro/bespoke company with <span className="text-zinc-300 font-medium">no Stripe charge</span> —
        the comped/invoiced path for the full platform tier. Links expire after the chosen window if unused.
      </p>

      <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-4 mb-6">
        <h2 className="text-sm font-medium text-zinc-300 mb-3">Generate invite</h2>
        <div className="flex gap-2">
          <input
            type="text"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Note (e.g. customer name)"
            className="flex-1 bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-emerald-700"
          />
          <input
            type="number"
            min={1}
            max={90}
            value={expiresDays}
            onChange={(e) => setExpiresDays(e.target.value)}
            title="Expires in (days)"
            className="w-20 bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-emerald-700"
          />
          <button
            onClick={generate}
            disabled={generating}
            className="px-4 py-2 bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white text-sm font-medium rounded transition-colors flex items-center gap-2"
          >
            <Link className="w-4 h-4" />
            Generate
          </button>
        </div>
        {error && <p className="mt-2 text-sm text-red-400">{error}</p>}
        {newInvite && (
          <div className="mt-3">
            <LinkRow label="Invite" url={newInvite.invite_url} copied={copied} onCopy={copyUrl} />
          </div>
        )}
      </div>

      <div className="bg-zinc-900 border border-zinc-800 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-800">
              <th className="text-left px-4 py-3 text-xs text-zinc-500 uppercase tracking-wide font-medium">Note</th>
              <th className="text-left px-4 py-3 text-xs text-zinc-500 uppercase tracking-wide font-medium">Created</th>
              <th className="text-left px-4 py-3 text-xs text-zinc-500 uppercase tracking-wide font-medium">Status</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {invites.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-zinc-500 text-sm">No invites generated yet</td>
              </tr>
            )}
            {invites.map((inv) => (
              <tr key={inv.id} className="border-b border-zinc-800 last:border-0">
                <td className="px-4 py-3 text-zinc-300">{inv.note ?? <span className="text-zinc-600">—</span>}</td>
                <td className="px-4 py-3 text-zinc-400">{new Date(inv.created_at).toLocaleDateString()}</td>
                <td className="px-4 py-3">
                  {inv.status === 'used' ? (
                    <span className="text-zinc-500 text-xs">
                      Used by {inv.used_by_company_name ?? 'unknown'} · {inv.used_at ? new Date(inv.used_at).toLocaleDateString() : ''}
                    </span>
                  ) : inv.status === 'pending' ? (
                    <span className="inline-flex items-center gap-1 text-xs text-emerald-400 bg-emerald-950 px-2 py-0.5 rounded-full">
                      Available · expires {new Date(inv.expires_at).toLocaleDateString()}
                    </span>
                  ) : (
                    <span className="text-xs text-zinc-500 capitalize">{inv.status}</span>
                  )}
                </td>
                <td className="px-4 py-3 text-right">
                  {inv.status === 'pending' && (
                    <div className="flex items-center justify-end gap-2">
                      <CopyChip label="Invite" url={inv.invite_url} copied={copied} onCopy={copyUrl} />
                      <button
                        onClick={() => cancelInvite(inv.id)}
                        className="text-zinc-600 hover:text-red-400 transition-colors"
                        title="Cancel invite"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

function LinkRow({
  label,
  url,
  copied,
  onCopy,
}: {
  label: string
  url: string
  copied: string | null
  onCopy: (url: string) => void
}) {
  return (
    <div className="flex items-center gap-2 bg-zinc-800 rounded px-3 py-2">
      <span className="text-[10px] uppercase tracking-wider text-zinc-500 w-14 shrink-0">{label}</span>
      <span className="flex-1 text-xs text-zinc-300 truncate font-mono">{url}</span>
      <button
        onClick={() => onCopy(url)}
        className="text-zinc-400 hover:text-zinc-100 transition-colors shrink-0"
      >
        {copied === url ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
      </button>
    </div>
  )
}

function CopyChip({
  label,
  url,
  copied,
  onCopy,
}: {
  label: string
  url: string
  copied: string | null
  onCopy: (url: string) => void
}) {
  return (
    <button
      onClick={() => onCopy(url)}
      className="inline-flex items-center gap-1 text-[11px] text-zinc-400 hover:text-zinc-100 border border-zinc-700 rounded px-1.5 py-0.5 transition-colors"
      title={`Copy ${label} signup URL`}
    >
      {copied === url ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
      {label}
    </button>
  )
}
