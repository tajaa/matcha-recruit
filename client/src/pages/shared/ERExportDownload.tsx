import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { Button, Logo } from '../../components/ui'

const BASE = import.meta.env.VITE_API_URL ?? '/api'

export default function ERExportDownload() {
  const { token } = useParams<{ token: string }>()
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [downloaded, setDownloaded] = useState(false)

  async function handleDownload(e: React.FormEvent) {
    e.preventDefault()
    if (!password.trim() || !token) return
    setError('')
    setLoading(true)
    try {
      const res = await fetch(`${BASE}/shared/er-export/${token}/download`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      })
      if (res.status === 404) { setError('Link not found or has been revoked.'); return }
      if (res.status === 410) { setError('This link has expired.'); return }
      if (res.status === 429) { setError('Too many failed attempts. Please try again later.'); return }
      if (res.status === 401 || res.status === 403) { setError('Incorrect password.'); return }
      if (!res.ok) { setError(`Download failed (${res.status}).`); return }

      const blob = await res.blob()
      const disposition = res.headers.get('content-disposition')
      const filename = disposition?.match(/filename="?(.+?)"?$/)?.[1] ?? 'er-case-export.pdf'
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
      setDownloaded(true)
      setPassword('')
    } catch {
      setError('Network error. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-zinc-900 flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <Logo className="justify-center mb-8 grayscale" />

        <div className="border border-zinc-800 rounded-xl p-6">
          <h1 className="text-lg font-semibold text-zinc-100 mb-1">
            ER Case Export
          </h1>
          <p className="text-sm text-zinc-500 mb-5">
            Enter the password to download this case file.
          </p>

          <form onSubmit={handleDownload} className="space-y-4">
            <div>
              <label htmlFor="password" className="block text-xs font-medium text-zinc-400 mb-1.5 uppercase">
                Password
              </label>
              <input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter password"
                className="w-full rounded-lg border border-zinc-700 bg-zinc-900/80 px-3.5 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-zinc-500 focus:ring-1 focus:ring-zinc-500 transition-colors"
              />
            </div>

            {error && <p className="text-sm text-red-400">{error}</p>}
            {downloaded && <p className="text-sm text-emerald-400">Download started.</p>}

            <Button
              type="submit"
              variant="secondary"
              className="w-full uppercase border border-zinc-600"
              disabled={loading || !password.trim()}
            >
              {loading ? 'Downloading...' : 'Download'}
            </Button>
          </form>
        </div>
      </div>
    </div>
  )
}
