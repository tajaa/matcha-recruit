import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { WcQuarter } from './IRWcMetricsCard'

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload || payload.length === 0) return null
  const lostDays = payload[0]?.payload?.lost_days ?? 0
  return (
    <div className="bg-zinc-900 border border-white/10 px-4 py-3 shadow-xl text-xs rounded-lg min-w-[160px]">
      <div className="text-zinc-500 font-mono text-[9px] uppercase tracking-widest mb-2">{label}</div>
      {payload.filter((p: any) => p.value > 0).reverse().map((entry: any) => (
        <div key={entry.dataKey} className="flex items-center justify-between gap-6">
          <span className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: entry.color }} />
            <span className="text-zinc-400 capitalize">{(entry.name || entry.dataKey).replace(/_/g, ' ')}</span>
          </span>
          <span className="font-mono text-zinc-200">{entry.value}</span>
        </div>
      ))}
      {lostDays > 0 && (
        <div className="flex items-center justify-between gap-6 mt-2 pt-2 border-t border-white/5">
          <span className="text-zinc-500">Lost days</span>
          <span className="font-mono text-amber-400">{lostDays}</span>
        </div>
      )}
    </div>
  )
}

export function IRQuarterlyRecordableChart({ quarterly }: { quarterly: WcQuarter[] }) {
  if (!quarterly || quarterly.length === 0) return null

  const data = quarterly.map((q) => ({
    quarter: q.quarter,
    'Non-DART': q.non_dart,
    DART: q.dart,
    lost_days: q.lost_days,
  }))

  return (
    <div>
      <h2 className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-3">
        OSHA Recordables by Quarter · trailing 8Q
      </h2>
      <div className="bg-zinc-900 border border-white/10 rounded-2xl p-5">
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="rgba(255,255,255,0.04)" strokeDasharray="2 4" />
            <XAxis
              dataKey="quarter"
              tick={{ fontSize: 10, fill: '#71717a', fontFamily: 'ui-monospace, monospace' }}
              axisLine={{ stroke: 'rgba(255,255,255,0.05)' }}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 10, fill: '#71717a', fontFamily: 'ui-monospace, monospace' }}
              axisLine={{ stroke: 'rgba(255,255,255,0.05)' }}
              tickLine={false}
              width={28}
              allowDecimals={false}
            />
            <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(255,255,255,0.03)' }} />
            <Bar dataKey="Non-DART" stackId="a" fill="#f59e0b" fillOpacity={0.7} radius={[0, 0, 0, 0]} />
            <Bar dataKey="DART" stackId="a" fill="#ef4444" fillOpacity={0.85} radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
        <div className="flex items-center gap-4 mt-3 text-[10px] font-mono uppercase tracking-widest text-zinc-500">
          <span className="inline-flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 bg-red-500/80" />
            DART (lost-time)
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 bg-amber-500/70" />
            Non-DART recordable
          </span>
        </div>
      </div>
    </div>
  )
}
