export const DISPOSITION_BADGE: Record<string, string> = {
  universal_in_domain: 'border-emerald-500/30 bg-emerald-500/15 text-emerald-300',
  category_specific: 'border-sky-500/30 bg-sky-500/15 text-sky-300',
  conditional: 'border-amber-500/30 bg-amber-500/15 text-amber-300',
  excluded: 'border-zinc-500/30 bg-zinc-500/15 text-zinc-400',
}

export function pct(n: number, d: number): number {
  return d > 0 ? Math.round((100 * n) / d) : 0
}
