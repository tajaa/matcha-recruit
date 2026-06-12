// Cappe dashboard — dark design system.
// Shared Tailwind class atoms so every Cappe surface stays cohesive + designed.
// Palette: near-black canvas (zinc-950), raised panels (zinc-900) on zinc-800
// hairlines, emerald accent. Keep these in sync; don't hand-roll one-off colors.

export const ui = {
  page: 'min-h-screen bg-zinc-950 text-zinc-100',
  card: 'rounded-xl border border-zinc-800 bg-zinc-900',
  cardHover: 'rounded-xl border border-zinc-800 bg-zinc-900 transition hover:border-zinc-700',
  input:
    'w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500',
  label: 'mb-1 block text-sm font-medium text-zinc-300',
  btnPrimary:
    'inline-flex items-center justify-center gap-2 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-zinc-950 transition hover:bg-emerald-400 disabled:opacity-60',
  btnGhost:
    'inline-flex items-center justify-center gap-2 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm font-medium text-zinc-200 transition hover:bg-zinc-800 disabled:opacity-60',
  heading: 'text-2xl font-semibold tracking-tight text-zinc-50',
  subtitle: 'text-sm text-zinc-400',
  muted: 'text-zinc-500',
  divider: 'border-zinc-800',
  danger: 'text-red-400 hover:text-red-300',
  accentText: 'text-emerald-400 hover:text-emerald-300',
  badge: 'rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase',
}

// Status → badge classes. Covers site/page, order, subscriber, booking, campaign.
export const statusBadge: Record<string, string> = {
  published: 'bg-emerald-500/15 text-emerald-400',
  active: 'bg-emerald-500/15 text-emerald-400',
  paid: 'bg-emerald-500/15 text-emerald-400',
  confirmed: 'bg-emerald-500/15 text-emerald-400',
  subscribed: 'bg-emerald-500/15 text-emerald-400',
  sent: 'bg-emerald-500/15 text-emerald-400',
  draft: 'bg-zinc-800 text-zinc-400',
  pending: 'bg-amber-500/15 text-amber-400',
  scheduled: 'bg-amber-500/15 text-amber-400',
  fulfilled: 'bg-sky-500/15 text-sky-400',
  archived: 'bg-zinc-800 text-zinc-500',
  cancelled: 'bg-zinc-800 text-zinc-500',
  unsubscribed: 'bg-zinc-800 text-zinc-500',
  refunded: 'bg-zinc-800 text-zinc-500',
  bounced: 'bg-red-500/15 text-red-400',
}

export const badgeFor = (status: string): string =>
  `${ui.badge} ${statusBadge[status] || statusBadge.draft}`
