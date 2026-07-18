import type { PropertyBuilding } from '../../../types/property'

export const inputCls = 'w-full bg-zinc-900 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-500'

export function fmtUsd(n: number | null): string {
  if (n == null) return '—'
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1)}M`
  if (Math.abs(n) >= 1_000) return `$${Math.round(n / 1000)}K`
  return `$${Math.round(n)}`
}

export const WORST_PERIL = (b: PropertyBuilding) => {
  const order = ['severe', 'high', 'elevated', 'moderate', 'low']
  const tiers = b.perils.map((p) => p.tier).filter(Boolean) as string[]
  return tiers.sort((a, z) => order.indexOf(a) - order.indexOf(z))[0] ?? null
}
