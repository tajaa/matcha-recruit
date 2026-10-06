import { centsToMoney } from '../../../components/SurfaceShell'

export const hhmm = (t: string) => t.slice(0, 5)
/** A price in the store's currency (see useBookings: `currency`). */
export const money = (cents: number | null | undefined, currency = 'USD') =>
  cents == null ? '—' : centsToMoney(cents, currency)

export const statusStyle: Record<string, string> = {
  pending: 'bg-amber-500/15 text-amber-400',
  confirmed: 'bg-emerald-500/15 text-emerald-400',
  declined: 'bg-red-500/15 text-red-400',
  cancelled: 'bg-zinc-800 text-zinc-500',
  completed: 'bg-sky-500/15 text-sky-400',
}

export const inputCls = 'rounded-lg border border-zinc-700 bg-zinc-950 text-zinc-100 placeholder:text-zinc-500 px-3 py-2 text-sm outline-none focus:border-emerald-500'
