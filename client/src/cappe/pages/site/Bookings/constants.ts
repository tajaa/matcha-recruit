export const hhmm = (t: string) => t.slice(0, 5)
export const money = (cents: number | null | undefined) =>
  cents == null ? '—' : `$${(cents / 100).toFixed(2)}`

export const statusStyle: Record<string, string> = {
  pending: 'bg-amber-500/15 text-amber-400',
  confirmed: 'bg-emerald-500/15 text-emerald-400',
  declined: 'bg-red-500/15 text-red-400',
  cancelled: 'bg-zinc-800 text-zinc-500',
  completed: 'bg-sky-500/15 text-sky-400',
}

export const inputCls = 'rounded-lg border border-zinc-700 bg-zinc-950 text-zinc-100 placeholder:text-zinc-500 px-3 py-2 text-sm outline-none focus:border-emerald-500'
