import { useState, useEffect } from 'react'
import { api } from '../../api/client'
import { Button } from '../ui'

export function IRAnonymousReportingPanel() {
  const [status, setStatus] = useState<{ enabled: boolean; link?: string } | null>(null)
  const [loading, setLoading] = useState(false)
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    if (expanded && !status) {
      api.get<{ enabled: boolean; link?: string }>('/ir/incidents/anonymous-reporting/status')
        .then(setStatus)
        .catch(() => setStatus({ enabled: false }))
    }
  }, [expanded, status])

  async function generateLink() {
    setLoading(true)
    try {
      const res = await api.post<{ link: string }>('/ir/incidents/anonymous-reporting/generate')
      setStatus({ enabled: true, link: res.link })
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }

  async function disable() {
    setLoading(true)
    try {
      await api.delete('/ir/incidents/anonymous-reporting/disable')
      setStatus({ enabled: false })
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }

  return (
    <div className="border border-zinc-800 rounded-lg">
      <button type="button" onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-3 text-left">
        <span className="text-xs font-medium text-zinc-400 uppercase tracking-wide">Anonymous Reporting</span>
        <span className="text-xs text-zinc-600">{expanded ? '\u2212' : '+'}</span>
      </button>
      {expanded && (
        <div className="px-4 pb-4 space-y-3">
          {!status ? (
            <p className="text-sm text-zinc-500">Loading...</p>
          ) : (
            <>
              {status.link && (
                <div className="flex items-center gap-2">
                  <input readOnly value={status.link} className="flex-1 bg-zinc-900 border border-zinc-800 rounded text-xs text-zinc-300 px-2 py-1.5 font-mono" />
                  <Button size="sm" variant="ghost" onClick={() => navigator.clipboard.writeText(status.link!)}>Copy</Button>
                </div>
              )}
              <div className="flex items-center gap-2">
                <Button size="sm" disabled={loading} onClick={generateLink}>
                  {status.link ? 'Regenerate Link' : 'Generate Link'}
                </Button>
                {status.enabled && (
                  <Button size="sm" variant="ghost" disabled={loading} onClick={disable}>Disable</Button>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
