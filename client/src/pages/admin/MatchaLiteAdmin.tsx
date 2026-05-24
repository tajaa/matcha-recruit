import { useState, useEffect } from 'react'
import { Copy, Check, Link, Trash2 } from 'lucide-react'
import { api } from '../../api/client'

type InviteToken = {
  id: string
  token: string
  note: string | null
  signup_url: string
  created_at: string
  used_at: string | null
  company_name: string | null
}

export default function MatchaLiteAdmin() {
  const [tokens, setTokens] = useState<InviteToken[]>([])
  const [note, setNote] = useState('')
  const [generating, setGenerating] = useState(false)
  const [newUrl, setNewUrl] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function load() {
    const data = await api.get<InviteToken[]>('/admin/matcha-lite/invite-tokens')
    setTokens(data)
  }

  useEffect(() => { load() }, [])

  async function generate() {
    setGenerating(true)
    setError(null)
    setNewUrl(null)
    try {
      const res = await api.post<InviteToken>('/admin/matcha-lite/invite-tokens', { note: note.trim() || null })
      setNewUrl(res.signup_url)
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
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  async function deleteToken(id: string) {
    if (!confirm('Delete this unused signup link?')) return
    await api.delete(`/admin/matcha-lite/invite-tokens/${id}`)
    await load()
  }

  return (
    <div className="p-6 max-w-3xl">
      <h1 className="text-xl font-semibold text-zinc-100 mb-6">Matcha Lite — Signup Links</h1>

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
        {newUrl && (
          <div className="mt-3 flex items-center gap-2 bg-zinc-800 rounded px-3 py-2">
            <span className="flex-1 text-xs text-zinc-300 truncate font-mono">{newUrl}</span>
            <button
              onClick={() => copyUrl(newUrl)}
              className="text-zinc-400 hover:text-zinc-100 transition-colors shrink-0"
            >
              {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
            </button>
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
                      <button
                        onClick={() => copyUrl(t.signup_url)}
                        className="text-zinc-400 hover:text-zinc-100 transition-colors"
                        title="Copy signup URL"
                      >
                        <Copy className="w-4 h-4" />
                      </button>
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
    </div>
  )
}
