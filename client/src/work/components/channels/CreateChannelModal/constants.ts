import type { AccessModel } from './types'

export const STEP_LABELS: Record<number, string> = {
  1: 'Basics',
  2: 'Access Model',
  3: 'Pricing',
  4: 'Engagement',
  5: 'Review',
  6: 'Management',
}

export const PRICE_SUGGESTIONS = [5, 10, 15, 25, 50]

export const INACTIVITY_OPTIONS = [
  { value: 7, label: '7 days' },
  { value: 14, label: '14 days' },
  { value: 21, label: '21 days' },
  { value: 30, label: '30 days' },
]

export const WARNING_OPTIONS = [
  { value: 1, label: '1 day' },
  { value: 2, label: '2 days' },
  { value: 3, label: '3 days' },
  { value: 5, label: '5 days' },
  { value: 7, label: '7 days' },
]

export function getApplicableSteps(accessModel: AccessModel): number[] {
  switch (accessModel) {
    case 'free':
      return [1, 2, 5]
    case 'paid':
      return [1, 2, 3, 5, 6]
    case 'paid_engagement':
      return [1, 2, 3, 4, 5, 6]
  }
}
