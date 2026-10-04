export const SCHEDULING_PLANS = [
  {
    id: 'basic', name: 'Basic', price: 49, audience: 'Build the week.',
    detail: 'The essentials for a hands-on manager.', featured: false,
    features: ['Manual schedules and reusable templates', 'Employee schedules, availability, time off, and swaps', 'Core assignment checks and manual break planning'],
  },
  {
    id: 'pro', name: 'Pro', price: 99, audience: 'Balance the floor.',
    detail: 'Bring breaks, coverage, and cost together.', featured: false,
    features: ['Everything in Basic', 'Automatic break staggering and relief review', 'Planned break reminders with configured delivery', 'Scheduled labor cost and overtime projections'],
  },
  {
    id: 'autopilot', name: 'Autopilot', price: 149, audience: 'Start with a draft.',
    detail: 'Let demand shape the week. You make the call.', featured: true,
    features: ['Everything in Pro', 'Sales- and weather-informed weekly drafts', 'Conversational changes with manager confirmation', 'Planning scenarios and schedule intelligence'],
  },
] as const

export type PlanId = typeof SCHEDULING_PLANS[number]['id']
export const planById = (id: PlanId) => SCHEDULING_PLANS.find((plan) => plan.id === id)!
