import { OshaLogsPanel } from '../../../components/ir/OshaLogsPanel'

export default function OshaLogs() {
  // Same page frame as Compliance/Dashboard/Onboarding/Company. OshaLogsPanel
  // already builds its own surfaces on bg-zinc-900 (not -950), so nothing
  // inside it dissolves into the new zinc-950 canvas — only the wrapper here
  // changes.
  return (
    <div className="overflow-hidden rounded-xl border border-white/[0.06] bg-zinc-950">
      <div className="border-b border-white/[0.06] px-5 py-4">
        <h1 className="text-2xl font-light tracking-tight text-zinc-50">OSHA Logs</h1>
        <p className="mt-1 text-[10px] text-zinc-500 font-mono uppercase tracking-wider">
          OSHA 300, 300A, and 301 recordkeeping
        </p>
      </div>
      <div className="p-5">
        <OshaLogsPanel />
      </div>
    </div>
  )
}
