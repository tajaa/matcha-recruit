import { AdminInput, AdminButton, AdminTable } from '../AdminUI'
import { useState } from 'react'
import { useAsync } from '../../../hooks/useAsync'
import { fetchIntegrityCheck, runStalenessCheck } from '../../../api/compliance'

function Section({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  const [open, setOpen] = useState(count > 0)
  return (
    <div className="border border-zinc-700/50 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-3 bg-zinc-800/50 hover:bg-zinc-800 text-left"
      >
        <span className="text-sm font-medium text-zinc-200">{title}</span>
        <div className="flex items-center gap-2">
          <span className={`px-2 py-0.5 text-xs font-bold rounded ${count > 0 ? 'bg-red-500/20 text-red-400' : 'bg-zinc-700 text-zinc-500'}`}>
            {count}
          </span>
          <span className="text-zinc-600">{open ? '▾' : '▸'}</span>
        </div>
      </button>
      {open && <div className="p-1">{children}</div>}
    </div>
  )
}

function stalenessLabel(level: string) {
  switch (level) {
    case 'expired': return <span className="text-red-400 font-bold">EXPIRED</span>
    case 'critical': return <span className="text-red-400">CRITICAL</span>
    case 'warning': return <span className="text-yellow-400">WARNING</span>
    default: return <span className="text-zinc-500">{level}</span>
  }
}

export default function IntegrityTab() {
  const [running, setRunning] = useState(false)
  const [stateFilter, setStateFilter] = useState('')

  const { data, loading, reload: load } = useAsync(
    () => fetchIntegrityCheck(stateFilter ? { state: stateFilter } : undefined),
    [stateFilter],
    null,
  )

  const handleRunCheck = async () => {
    setRunning(true)
    try {
      const result = await runStalenessCheck(stateFilter ? { state: stateFilter } : undefined)
      alert(`Created ${result.alerts_created} alerts, resolved ${result.alerts_resolved}, found ${result.stale_found} stale + ${result.missing_found} missing`)
      load()
    } catch {
      // ignore
    } finally {
      setRunning(false)
    }
  }

  if (loading) return <div className="text-zinc-500 py-12 text-center">Loading integrity check...</div>
  if (!data) return <div className="text-zinc-500 py-12 text-center">Failed to load</div>

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-3 flex-wrap">
        <AdminInput
          type="text"
          placeholder="Filter by state (e.g. CA)"
          value={stateFilter}
          onChange={e => setStateFilter(e.target.value.toUpperCase())}
          className="w-40 uppercase"
          maxLength={2}
        />
        <AdminButton
          onClick={handleRunCheck}
          disabled={running}
          className="text-amber-400 disabled:opacity-50" variant="ghost"
        >
          {running ? 'Running...' : 'Run Staleness Check'}
        </AdminButton>
        <div className="ml-auto flex items-center gap-4 text-xs text-zinc-500">
          <span>Defined: <strong className="text-zinc-300">{data.total_defined_keys}</strong></span>
          <span>Records: <strong className="text-zinc-300">{data.total_db_records}</strong></span>
          <span>Linked: <strong className="text-zinc-300">{data.linked_records}</strong></span>
          <span>Score: <strong className={data.integrity_score > 50 ? 'text-green-400' : 'text-red-400'}>{data.integrity_score}%</strong></span>
        </div>
      </div>

      {/* Missing Keys */}
      <Section title="Missing Keys" count={data.missing_count}>
        {data.missing_keys.length === 0 ? (
          <div className="px-4 py-3 text-sm text-zinc-500">No missing keys</div>
        ) : (
          <AdminTable>
            <thead >
              <tr>
                <th >Jurisdiction</th>
                <th >Category</th>
                <th >Key</th>
                <th className="text-center">Weight</th>
                <th >Group</th>
              </tr>
            </thead>
            <tbody>
              {data.missing_keys.slice(0, 100).map((mk, i) => (
                <tr key={i} className="border-t border-zinc-800/30">
                  <td className="text-zinc-300">{mk.city}, {mk.state}</td>
                  <td className="text-zinc-400">{mk.category}</td>
                  <td className="text-red-400 font-mono">{mk.key}</td>
                  <td className="text-center">{mk.weight > 1 ? <span className="text-purple-300">{mk.weight}x</span> : '1x'}</td>
                  <td className="text-zinc-500">{mk.key_group || '—'}</td>
                </tr>
              ))}
            </tbody>
          </AdminTable>
        )}
        {data.missing_count > 100 && (
          <div className="px-4 py-2 text-xs text-zinc-500">Showing 100 of {data.missing_count}</div>
        )}
      </Section>

      {/* Stale Keys */}
      <Section title="Stale Keys" count={data.stale_count}>
        {data.stale_keys.length === 0 ? (
          <div className="px-4 py-3 text-sm text-zinc-500">No stale keys</div>
        ) : (
          <AdminTable>
            <thead >
              <tr>
                <th >Jurisdiction</th>
                <th >Category</th>
                <th >Key</th>
                <th className="text-center">Days</th>
                <th >Level</th>
              </tr>
            </thead>
            <tbody>
              {data.stale_keys.map((sk, i) => (
                <tr key={i} className="border-t border-zinc-800/30">
                  <td className="text-zinc-300">{sk.city}, {sk.state}</td>
                  <td className="text-zinc-400">{sk.category}</td>
                  <td className="font-mono text-zinc-300">{sk.key_name}</td>
                  <td className="text-center font-mono">{sk.days_since_verified}</td>
                  <td >{stalenessLabel(sk.staleness_level)}</td>
                </tr>
              ))}
            </tbody>
          </AdminTable>
        )}
      </Section>

      {/* Partial Groups */}
      <Section title="Partial Groups" count={data.partial_group_count}>
        {data.partial_groups.length === 0 ? (
          <div className="px-4 py-3 text-sm text-zinc-500">No partial groups</div>
        ) : (
          <AdminTable>
            <thead >
              <tr>
                <th >Jurisdiction</th>
                <th >Group</th>
                <th >Coverage</th>
                <th >Missing Keys</th>
              </tr>
            </thead>
            <tbody>
              {data.partial_groups.map((pg, i) => (
                <tr key={i} className="border-t border-zinc-800/30">
                  <td className="text-zinc-300">{pg.city}, {pg.state}</td>
                  <td className="text-yellow-400">{pg.key_group}</td>
                  <td className="font-mono">{pg.present}/{pg.expected} ({pg.coverage_pct}%)</td>
                  <td className="text-zinc-500 font-mono">
                    {pg.missing.join(', ')}
                  </td>
                </tr>
              ))}
            </tbody>
          </AdminTable>
        )}
      </Section>

      {/* Orphaned Records */}
      <Section title="Orphaned Records" count={data.orphaned_count}>
        {data.orphaned_records.length === 0 ? (
          <div className="px-4 py-3 text-sm text-zinc-500">No orphaned records</div>
        ) : (
          <AdminTable>
            <thead >
              <tr>
                <th >Jurisdiction</th>
                <th >Category</th>
                <th >Regulation Key</th>
                <th >Title</th>
                <th >Tier</th>
              </tr>
            </thead>
            <tbody>
              {data.orphaned_records.slice(0, 100).map((or, i) => (
                <tr key={i} className="border-t border-zinc-800/30">
                  <td className="text-zinc-300">{or.city}, {or.state}</td>
                  <td className="text-zinc-400">{or.category}</td>
                  <td className="font-mono text-zinc-500 max-w-xs truncate">{or.regulation_key}</td>
                  <td className="text-zinc-400 max-w-xs truncate">{or.title}</td>
                  <td className="text-zinc-500">{or.source_tier}</td>
                </tr>
              ))}
            </tbody>
          </AdminTable>
        )}
        {data.orphaned_count > 100 && (
          <div className="px-4 py-2 text-xs text-zinc-500">Showing 100 of {data.orphaned_count}</div>
        )}
      </Section>
    </div>
  )
}
