import { OshaLogsPanel } from '../../components/ir/OshaLogsPanel'

export default function OshaLogs() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-100">OSHA Logs</h1>
        <p className="mt-1 text-[10px] text-zinc-500 font-mono uppercase tracking-wider">
          OSHA 300, 300A, and 301 recordkeeping
        </p>
      </div>
      <OshaLogsPanel />
    </div>
  )
}
