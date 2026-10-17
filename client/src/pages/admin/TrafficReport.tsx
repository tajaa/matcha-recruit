import { AdminPageHeader } from '../../components/admin/AdminPageHeader'
import { useCallback, useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
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
      <AdminPageHeader
        title="Traffic"
        description={<>all sites · refreshed every 15 min</>}
        actions={
          <button
            onClick={() => void load()}
            className="flex items-center gap-1.5 rounded-md border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-800"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        }
      />
      {error ? (
        <div className="p-6 text-sm text-zinc-400">
          {error.includes('404')
            ? 'Report not generated in this environment (prod host writes it every 15 min).'
            : error}
        </div>
      ) : html ? (
        <iframe
          title="Traffic report"
          srcDoc={html}
          sandbox="allow-scripts"
          className="h-[70vh] min-h-96 w-full rounded-lg border border-zinc-800"
        />
      ) : (
        <div className="p-6 text-sm text-zinc-500">Loading…</div>
      )}
    </div>
  )
}
