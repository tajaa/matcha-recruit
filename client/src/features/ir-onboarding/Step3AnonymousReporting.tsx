import { useEffect, useState } from 'react'
import { Loader2, Copy, Check } from 'lucide-react'
import { api } from '../../api/client'

interface AnonymousStatus {
  token: string | null
  link?: string | null
  enabled: boolean
  used: boolean
}

const PUBLIC_REPORT_BASE = `${window.location.origin}/report`

export default function Step3AnonymousReporting({ onDone }: { onDone: () => void }) {
  const [status, setStatus] = useState<AnonymousStatus | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.get<AnonymousStatus>('/ir/incidents/anonymous-reporting/status')
      .then(setStatus)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load status'))
  }, [])

  async function generate() {
    setSubmitting(true)
    setError(null)
    try {
      const res = await api.post<AnonymousStatus>('/ir/incidents/anonymous-reporting/generate')
      setStatus(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to generate token')
    } finally {
      setSubmitting(false)
    }
  }

  const publicLink = status?.link ?? (status?.token ? `${PUBLIC_REPORT_BASE}/${status.token}` : null)

  function copyLink() {
    if (!publicLink) return
    navigator.clipboard.writeText(publicLink)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-zinc-100 mb-1">Anonymous reporting</h2>
        <p className="text-sm text-zinc-400">
          Generate a public link your employees can use to file incidents anonymously. Optional — you can skip and add later.
        </p>
      </div>

      <div className="bg-zinc-900/40 border border-zinc-800 rounded p-4">
        {publicLink ? (
          <>
            <p className="text-xs text-zinc-500 mb-2">Public reporting link</p>
            <div className="flex items-center gap-2">
              <code className="flex-1 bg-zinc-950 border border-zinc-800 rounded px-3 py-2 text-xs text-zinc-300 truncate">
                {publicLink}
              </code>
              <button
                onClick={copyLink}
                className="bg-zinc-800 hover:bg-zinc-700 text-zinc-200 px-3 py-2 rounded text-xs flex items-center gap-1"
              >
                {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                {copied ? 'Copied' : 'Copy'}
              </button>
            </div>
          </>
        ) : (
          <button
            onClick={generate}
            disabled={submitting}
            className="bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded flex items-center"
          >
            {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Generate link'}
          </button>
        )}
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}

      <div className="flex items-center gap-3">
        <button
          onClick={onDone}
          className="bg-emerald-700 hover:bg-emerald-600 text-white text-sm font-medium px-5 py-2 rounded transition-colors"
        >
          Continue
        </button>
        <button
          onClick={onDone}
          className="text-sm text-zinc-500 hover:text-zinc-300 underline"
        >
          Skip for now
        </button>
      </div>
    </div>
  )
}
