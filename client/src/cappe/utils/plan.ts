// Which Cappe plans carry premium design. Mirrors the server's single source
// of truth, `services/design_gate.py:PREMIUM_PLANS` — keep the two in step.
// `pro` is legacy (no longer sold) but existing accounts keep what they had.
export const PREMIUM_PLANS: ReadonlySet<string> = new Set(['pro', 'business', 'creator'])

export function isPremiumPlan(plan: string | null | undefined): boolean {
  return !!plan && PREMIUM_PLANS.has(plan)
}
