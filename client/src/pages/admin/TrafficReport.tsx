import { useCallback, useEffect, useState } from 'react'
import { BarChart3, RefreshCw } from 'lucide-react'
import { api } from '../../api/client'

/** Admin traffic dashboard — renders the goaccess report generated on the
 *  prod host (all vhosts: hey-matcha.com, gummfit.com, tenant subdomains).
 *  Regenerated every 15 min by the host's goaccess-report.timer. */
export default function TrafficReport() {
  const [html, setHtml] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setHtml(await api.getText('/admin/traffic-report'))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load report')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-zinc-200 px-4 py-3">
        <div className="flex items-center gap-2">
          <BarChart3 className="h-5 w-5 text-emerald-600" />
          <h1 className="text-lg font-semibold text-zinc-900">Traffic</h1>
          <span className="text-xs text-zinc-500">all sites · refreshed every 15 min</span>
        </div>
        <button
          onClick={() => void load()}
          className="flex items-center gap-1.5 rounded-md border border-zinc-300 px-3 py-1.5 text-sm text-zinc-700 hover:bg-zinc-50"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>
      {error ? (
        <div className="p-6 text-sm text-zinc-600">
          {error.includes('404')
            ? 'Report not generated in this environment (prod host writes it every 15 min).'
            : error}
        </div>
      ) : html ? (
        <iframe
          title="Traffic report"
          srcDoc={html}
          sandbox="allow-scripts"
          className="w-full flex-1 border-0"
        />
      ) : (
        <div className="p-6 text-sm text-zinc-500">Loading…</div>
      )}
    </div>
  )
}
