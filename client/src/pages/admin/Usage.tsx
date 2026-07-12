import { useCallback, useEffect, useState } from 'react'
import { Activity, RefreshCw, Trash2 } from 'lucide-react'
import { api } from '../../api/client'

type Totals = {
  dau: number
  wau: number
  mau: number
  active_companies_7d: number
  anon_visitors_7d: number
}

type DailyPoint = { day: string; users: number; visitors: number; page_views: number }
type TopPage = { surface: string; path: string; views: number; uniques: number }
type CompanyRow = {
  id: string
  name: string
  last_seen: string | null
  users: number
  events: number
}
type EndpointRow = {
  path: string
  method: string | null
  calls: number
  avg_ms: number
  p95_ms: number
  errors: number
}

type UsageSummary = {
  since_days: number
  totals: Totals
  daily: DailyPoint[]
  top_pages: TopPage[]
  companies: CompanyRow[]
  endpoints: EndpointRow[]
}

// Two categorical series, validated for CVD separation against the light and
// dark chart surfaces. Signed-in users carry the product's emerald; anonymous
// visitors take the indigo. Fixed assignment — never reordered by rank.
const COLOR_USERS = '#059669'
const COLOR_VISITORS = '#6366f1'

function StatCard({ label, value, hint }: { label: string; value: number; hint?: string }) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-zinc-900">{value.toLocaleString()}</div>
      {hint ? <div className="mt-0.5 text-xs text-zinc-500">{hint}</div> : null}
    </div>
  )
}

/** Grouped daily bars: signed-in users vs anonymous visitors. Inline SVG — the
 *  codebase has no chart library and doesn't want one. */
function DailyChart({ data }: { data: DailyPoint[] }) {
  if (data.length === 0) {
    return <div className="p-6 text-sm text-zinc-500">No activity in this window yet.</div>
  }

  const W = 720
  const H = 200
  const PAD_L = 32
  const PAD_B = 22
  const PAD_T = 8
  const plotW = W - PAD_L - 8
  const plotH = H - PAD_B - PAD_T

  const max = Math.max(1, ...data.map((d) => Math.max(d.users, d.visitors)))
  const slot = plotW / data.length
  const barW = Math.max(2, Math.min(14, slot / 2 - 2))

  const ticks = [0, Math.round(max / 2), max]

  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-[200px] w-full min-w-[560px]" role="img">
        {ticks.map((t) => {
          const y = PAD_T + plotH - (t / max) * plotH
          return (
            <g key={t}>
              <line x1={PAD_L} x2={W - 8} y1={y} y2={y} stroke="#e4e4e7" strokeWidth={1} />
              <text x={PAD_L - 6} y={y + 3} textAnchor="end" className="fill-zinc-400 text-[9px]">
                {t}
              </text>
            </g>
          )
        })}

        {data.map((d, i) => {
          const x = PAD_L + i * slot
          const uh = (d.users / max) * plotH
          const vh = (d.visitors / max) * plotH
          const label = new Date(d.day).toLocaleDateString(undefined, {
            month: 'short',
            day: 'numeric',
          })
          // Every ~5th day gets an axis label — denser collides on 30d windows.
          const showLabel = data.length <= 10 || i % Math.ceil(data.length / 6) === 0
          return (
            <g key={d.day}>
              <rect
                x={x + 1}
                y={PAD_T + plotH - uh}
                width={barW}
                height={uh}
                rx={2}
                fill={COLOR_USERS}
              >
                <title>{`${label} — ${d.users} users, ${d.page_views} page views`}</title>
              </rect>
              <rect
                x={x + barW + 3}
                y={PAD_T + plotH - vh}
                width={barW}
                height={vh}
                rx={2}
                fill={COLOR_VISITORS}
              >
                <title>{`${label} — ${d.visitors} anonymous visitors`}</title>
              </rect>
              {showLabel ? (
                <text
                  x={x + barW}
                  y={H - 6}
                  textAnchor="middle"
                  className="fill-zinc-400 text-[9px]"
                >
                  {label}
                </text>
              ) : null}
            </g>
          )
        })}
        <line
          x1={PAD_L}
          x2={W - 8}
          y1={PAD_T + plotH}
          y2={PAD_T + plotH}
          stroke="#d4d4d8"
          strokeWidth={1}
        />
      </svg>
    </div>
  )
}

function Legend() {
  return (
    <div className="flex items-center gap-4 text-xs text-zinc-600">
      <span className="flex items-center gap-1.5">
        <span
          className="inline-block h-2.5 w-2.5 rounded-sm"
          style={{ background: COLOR_USERS }}
        />
        Signed-in users
      </span>
      <span className="flex items-center gap-1.5">
        <span
          className="inline-block h-2.5 w-2.5 rounded-sm"
          style={{ background: COLOR_VISITORS }}
        />
        Anonymous visitors
      </span>
    </div>
  )
}

export default function Usage() {
  const [data, setData] = useState<UsageSummary | null>(null)
  const [days, setDays] = useState(7)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await api.get<UsageSummary>(`/admin/usage/summary?since_days=${days}`))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load usage')
    } finally {
      setLoading(false)
    }
  }, [days])

  useEffect(() => {
    void load()
  }, [load])

  const purge = async () => {
    if (!confirm('Delete usage events older than 90 days?')) return
    try {
      const res = await api.delete<{ deleted: number }>('/admin/usage?older_than_days=90')
      alert(`Deleted ${res.deleted.toLocaleString()} events.`)
      void load()
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Purge failed')
    }
  }

  return (
    <div className="p-4">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Activity className="h-5 w-5 text-emerald-600" />
          <h1 className="text-lg font-semibold text-zinc-900">Usage</h1>
          <span className="text-xs text-zinc-500">who's active, and what they use</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded-md border border-zinc-300">
            {[7, 30].map((d) => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`px-3 py-1.5 text-sm first:rounded-l-md last:rounded-r-md ${
                  days === d ? 'bg-emerald-50 text-emerald-700' : 'text-zinc-600 hover:bg-zinc-50'
                }`}
              >
                {d}d
              </button>
            ))}
          </div>
          <button
            onClick={() => void load()}
            className="flex items-center gap-1.5 rounded-md border border-zinc-300 px-3 py-1.5 text-sm text-zinc-700 hover:bg-zinc-50"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          <button
            onClick={() => void purge()}
            className="flex items-center gap-1.5 rounded-md border border-zinc-300 px-3 py-1.5 text-sm text-zinc-600 hover:bg-zinc-50"
          >
            <Trash2 className="h-4 w-4" />
            Purge 90d+
          </button>
        </div>
      </div>

      {error ? (
        <div className="rounded-lg border border-zinc-200 p-6 text-sm text-zinc-600">{error}</div>
      ) : !data ? (
        <div className="p-6 text-sm text-zinc-500">Loading…</div>
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            <StatCard label="DAU" value={data.totals.dau} hint="last 24h" />
            <StatCard label="WAU" value={data.totals.wau} hint="last 7d" />
            <StatCard label="MAU" value={data.totals.mau} hint="last 30d" />
            <StatCard label="Companies" value={data.totals.active_companies_7d} hint="active 7d" />
            <StatCard label="Visitors" value={data.totals.anon_visitors_7d} hint="anon, 7d" />
          </div>

          <div className="rounded-lg border border-zinc-200 bg-white p-4">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-zinc-900">
                Daily activity — last {data.since_days} days
              </h2>
              <Legend />
            </div>
            <DailyChart data={data.daily} />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-lg border border-zinc-200 bg-white">
              <h2 className="border-b border-zinc-200 px-4 py-2.5 text-sm font-semibold text-zinc-900">
                Top pages
              </h2>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-zinc-500">
                    <th className="px-4 py-2 font-medium">Path</th>
                    <th className="px-4 py-2 font-medium">Surface</th>
                    <th className="px-4 py-2 text-right font-medium">Views</th>
                    <th className="px-4 py-2 text-right font-medium">Uniques</th>
                  </tr>
                </thead>
                <tbody>
                  {data.top_pages.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="px-4 py-4 text-zinc-500">
                        No page views yet.
                      </td>
                    </tr>
                  ) : (
                    data.top_pages.map((p) => (
                      <tr key={`${p.surface}${p.path}`} className="border-t border-zinc-100">
                        <td className="px-4 py-2 font-mono text-xs text-zinc-800">{p.path}</td>
                        <td className="px-4 py-2 text-xs text-zinc-500">{p.surface}</td>
                        <td className="px-4 py-2 text-right tabular-nums text-zinc-700">
                          {p.views.toLocaleString()}
                        </td>
                        <td className="px-4 py-2 text-right tabular-nums text-zinc-700">
                          {p.uniques.toLocaleString()}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <div className="rounded-lg border border-zinc-200 bg-white">
              <h2 className="border-b border-zinc-200 px-4 py-2.5 text-sm font-semibold text-zinc-900">
                Company activity
              </h2>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-zinc-500">
                    <th className="px-4 py-2 font-medium">Company</th>
                    <th className="px-4 py-2 font-medium">Last seen</th>
                    <th className="px-4 py-2 text-right font-medium">Users</th>
                    <th className="px-4 py-2 text-right font-medium">Events</th>
                  </tr>
                </thead>
                <tbody>
                  {data.companies.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="px-4 py-4 text-zinc-500">
                        No company activity yet.
                      </td>
                    </tr>
                  ) : (
                    data.companies.map((c) => (
                      <tr key={c.id} className="border-t border-zinc-100">
                        <td className="px-4 py-2 text-zinc-800">{c.name}</td>
                        <td className="px-4 py-2 text-xs text-zinc-500">
                          {c.last_seen ? new Date(c.last_seen).toLocaleString() : '—'}
                        </td>
                        <td className="px-4 py-2 text-right tabular-nums text-zinc-700">
                          {c.users}
                        </td>
                        <td className="px-4 py-2 text-right tabular-nums text-zinc-700">
                          {c.events.toLocaleString()}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="rounded-lg border border-zinc-200 bg-white">
            <h2 className="border-b border-zinc-200 px-4 py-2.5 text-sm font-semibold text-zinc-900">
              API endpoints
            </h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-zinc-500">
                    <th className="px-4 py-2 font-medium">Endpoint</th>
                    <th className="px-4 py-2 font-medium">Method</th>
                    <th className="px-4 py-2 text-right font-medium">Calls</th>
                    <th className="px-4 py-2 text-right font-medium">Avg</th>
                    <th className="px-4 py-2 text-right font-medium">p95</th>
                    <th className="px-4 py-2 text-right font-medium">5xx</th>
                  </tr>
                </thead>
                <tbody>
                  {data.endpoints.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="px-4 py-4 text-zinc-500">
                        No API calls recorded yet.
                      </td>
                    </tr>
                  ) : (
                    data.endpoints.map((e) => (
                      <tr key={`${e.method}${e.path}`} className="border-t border-zinc-100">
                        <td className="px-4 py-2 font-mono text-xs text-zinc-800">{e.path}</td>
                        <td className="px-4 py-2 text-xs text-zinc-500">{e.method}</td>
                        <td className="px-4 py-2 text-right tabular-nums text-zinc-700">
                          {e.calls.toLocaleString()}
                        </td>
                        <td className="px-4 py-2 text-right tabular-nums text-zinc-700">
                          {e.avg_ms}ms
                        </td>
                        <td className="px-4 py-2 text-right tabular-nums text-zinc-700">
                          {e.p95_ms}ms
                        </td>
                        <td
                          className={`px-4 py-2 text-right tabular-nums ${
                            e.errors > 0 ? 'font-medium text-red-600' : 'text-zinc-400'
                          }`}
                        >
                          {e.errors}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
