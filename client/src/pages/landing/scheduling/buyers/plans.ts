export const TIME_TASKS = [
  { id: 'schedule', label: 'Building and reviewing the schedule' },
  { id: 'requests', label: 'Availability, swaps, and shift requests' },
  { id: 'breaks', label: 'Planning breaks and relief' },
  { id: 'cost', label: 'Reviewing labor cost and overtime' },
] as const

export type TimeTask = typeof TIME_TASKS[number]['id']

export const SCHEDULING_PLANS = [
  {
    id: 'basic', name: 'Basic', price: 49, audience: 'Build the week.',
    detail: 'The essentials for a hands-on manager.', featured: false, laborCost: false,
    features: ['Manual schedules and reusable templates', 'Employee schedules, availability, time off, and swaps', 'Core assignment checks and manual break planning'],
    methods: {
      schedule: 'Reusable templates; you build and review the week.',
      requests: 'Employee requests in one place; you review the changes.',
      breaks: 'Manual break plans; you arrange timing and relief.',
      cost: 'Keep this work in your existing tools. Labor costing is not included.',
    },
  },
  {
    id: 'pro', name: 'Pro', price: 99, audience: 'Balance the floor.',
    detail: 'Bring breaks, coverage, and cost together.', featured: false, laborCost: true,
    features: ['Everything in Basic', 'Automatic break staggering and relief review', 'Planned break reminders with configured delivery', 'Scheduled labor cost and overtime projections'],
    methods: {
      schedule: 'Reusable templates; you build and review the week.',
      requests: 'Employee requests in one place; you review the changes.',
      breaks: 'Automatic staggering and relief review; allow time to check the plan.',
      cost: 'Scheduled labor cost and overtime projections; allow time to act on findings.',
    },
  },
  {
    id: 'autopilot', name: 'Autopilot', price: 149, audience: 'Start with a draft.',
    detail: 'Let demand shape the week. You make the call.', featured: true, laborCost: true,
    features: ['Everything in Pro', 'Sales- and weather-informed weekly drafts', 'Conversational changes with manager confirmation', 'Planning scenarios and schedule intelligence'],
    methods: {
      schedule: 'A demand-informed draft; include review, corrections, and publication.',
      requests: 'Conversational changes; include manager confirmation and follow-up.',
      breaks: 'Automatic staggering and relief review; allow time to check the plan.',
      cost: 'Cost projections and planning scenarios; allow time to act on findings.',
    },
  },
] as const

export type PlanId = typeof SCHEDULING_PLANS[number]['id']
export const planById = (id: PlanId) => SCHEDULING_PLANS.find((plan) => plan.id === id)!
