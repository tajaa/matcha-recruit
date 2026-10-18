export function StatusBadge({ status }: { status: string }) {
  if (!status || status === 'approved')
    return <span className="text-[10px] px-1.5 py-0.5 rounded border border-emerald-500/40 bg-emerald-500/10 text-emerald-300">Approved</span>
  if (status === 'pending')
    return <span className="text-[10px] px-1.5 py-0.5 rounded border border-amber-500/40 bg-amber-500/10 text-amber-300">Pending</span>
  return <span className="text-[10px] px-1.5 py-0.5 rounded border border-red-500/40 bg-red-500/10 text-red-300">{status}</span>
}
