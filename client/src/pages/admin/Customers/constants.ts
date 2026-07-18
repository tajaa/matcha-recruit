import type { Tab } from './types'

export const TAB_DEFS: { id: Tab; label: string; help: string }[] = [
  { id: 'all', label: 'All', help: 'Every customer in the system.' },
  { id: 'free', label: 'Free', help: 'resources_free signups — no paid features, audit + templates only.' },
  { id: 'lite', label: 'Matcha Lite', help: 'Stripe-billed self-serve bundle (IR + Resources).' },
  { id: 'x', label: 'Matcha-X', help: 'Stripe-billed mid tier — Lite parity now; HRIS + credentials later.' },
  { id: 'platform', label: 'Platform', help: 'Bespoke / sales-led companies on full feature set.' },
  { id: 'personal', label: 'Matcha Work Personal', help: 'role=individual, personal workspace, optional Stripe sub.' },
]

export const TIER_BADGE: Record<Exclude<Tab, 'all'>, string> = {
  free: 'border-zinc-600 bg-zinc-700/30 text-zinc-300',
  lite: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300',
  x: 'border-teal-500/40 bg-teal-500/10 text-teal-300',
  platform: 'border-violet-500/40 bg-violet-500/10 text-violet-300',
  personal: 'border-sky-500/40 bg-sky-500/10 text-sky-300',
}

export const TIER_LABEL: Record<Exclude<Tab, 'all'>, string> = {
  free: 'Free',
  lite: 'Lite',
  x: 'Matcha-X',
  platform: 'Platform',
  personal: 'Personal',
}
