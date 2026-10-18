/* eslint-disable react-hooks/set-state-in-effect -- Effects intentionally synchronize this tool with loaded data, URL selections, and preview inputs. */
import { AdminTab, AdminTabBar } from '../../../components/admin/AdminTabs'
import { AdminStat as StatCard, AdminCard, AdminButton, AdminTable } from '../../../components/admin/AdminUI'
import { AdminPageHeader } from '../../../components/admin/AdminPageHeader'
import { useCallback, useEffect, useState } from 'react'
import { RefreshCw, Trash2 } from 'lucide-react'
import { api } from '../../../api/client'

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
              <line x1={PAD_L} x2={W - 8} y1={y} y2={y} className="stroke-zinc-700" strokeWidth={1} />
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
    <div className="flex items-center gap-4 text-xs text-zinc-400">
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
    <div>
      <AdminPageHeader
        title="Usage"
        description="who's active, and what they use"
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <AdminTabBar className="mb-0!" role="group" aria-label="Time range">
              {[7, 30].map((d) => (
                <AdminTab key={d} active={days === d} onClick={() => setDays(d)}>
                  {d}d
                </AdminTab>
              ))}
            </AdminTabBar>
            <AdminButton
              onClick={() => void load()}
              className="gap-1.5" variant="secondary"
            >
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </AdminButton>
            <AdminButton
              onClick={() => void purge()}
              className="gap-1.5" variant="secondary"
            >
              <Trash2 className="h-4 w-4" />
              Purge 90d+
            </AdminButton>
          </div>
        }
      />

      {error ? (
        <div className="rounded-lg border border-zinc-800 p-6 text-sm text-zinc-400">{error}</div>
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

          <AdminCard >
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-zinc-100">
                Daily activity — last {data.since_days} days
              </h2>
              <Legend />
            </div>
            <DailyChart data={data.daily} />
          </AdminCard>

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50">
              <h2 className="border-b border-zinc-800 px-4 py-2.5 text-sm font-semibold text-zinc-100">
                Top pages
              </h2>
              <AdminTable>
                <thead>
                  <tr className="text-left text-xs text-zinc-500">
                    <th >Path</th>
                    <th >Surface</th>
                    <th className="text-right">Views</th>
                    <th className="text-right">Uniques</th>
                  </tr>
                </thead>
                <tbody>
                  {data.top_pages.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="text-zinc-500">
                        No page views yet.
                      </td>
                    </tr>
                  ) : (
                    data.top_pages.map((p) => (
                      <tr key={`${p.surface}${p.path}`} className="border-t border-zinc-800/60">
                        <td className="font-mono text-zinc-200">{p.path}</td>
                        <td className="text-zinc-500">{p.surface}</td>
                        <td className="text-right tabular-nums text-zinc-300">
                          {p.views.toLocaleString()}
                        </td>
                        <td className="text-right tabular-nums text-zinc-300">
                          {p.uniques.toLocaleString()}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </AdminTable>
            </div>

            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50">
              <h2 className="border-b border-zinc-800 px-4 py-2.5 text-sm font-semibold text-zinc-100">
                Company activity
              </h2>
              <AdminTable>
                <thead>
                  <tr className="text-left text-xs text-zinc-500">
                    <th >Company</th>
                    <th >Last seen</th>
                    <th className="text-right">Users</th>
                    <th className="text-right">Events</th>
                  </tr>
                </thead>
                <tbody>
                  {data.companies.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="text-zinc-500">
                        No company activity yet.
                      </td>
                    </tr>
                  ) : (
                    data.companies.map((c) => (
                      <tr key={c.id} className="border-t border-zinc-800/60">
                        <td className="text-zinc-200">{c.name}</td>
                        <td className="text-zinc-500">
                          {c.last_seen ? new Date(c.last_seen).toLocaleString() : '—'}
                        </td>
                        <td className="text-right tabular-nums text-zinc-300">
                          {c.users}
                        </td>
                        <td className="text-right tabular-nums text-zinc-300">
                          {c.events.toLocaleString()}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </AdminTable>
            </div>
          </div>

          <AdminCard >
            <h2 className="border-b border-zinc-800 px-4 py-2.5 text-sm font-semibold text-zinc-100">
              API endpoints
            </h2>
            <AdminTable>
              <thead>
                <tr className="text-left text-xs text-zinc-500">
                  <th >Endpoint</th>
                  <th >Method</th>
                  <th className="text-right">Calls</th>
                  <th className="text-right">Avg</th>
                  <th className="text-right">p95</th>
                  <th className="text-right">5xx</th>
                </tr>
              </thead>
              <tbody>
                {data.endpoints.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="text-zinc-500">
                      No API calls recorded yet.
                    </td>
                  </tr>
                ) : (
                  data.endpoints.map((e) => (
                    <tr key={`${e.method}${e.path}`} className="border-t border-zinc-800/60">
                      <td className="font-mono text-zinc-200">{e.path}</td>
                      <td className="text-zinc-500">{e.method}</td>
                      <td className="text-right tabular-nums text-zinc-300">
                        {e.calls.toLocaleString()}
                      </td>
                      <td className="text-right tabular-nums text-zinc-300">
                        {e.avg_ms}ms
                      </td>
                      <td className="text-right tabular-nums text-zinc-300">
                        {e.p95_ms}ms
                      </td>
                      <td
                        className={` text-right tabular-nums ${
                          e.errors > 0 ? 'text-red-600' : 'text-zinc-400'
                        }`}
                      >
                        {e.errors}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </AdminTable>
          </AdminCard>
        </div>
      )}
    </div>
  )
}
