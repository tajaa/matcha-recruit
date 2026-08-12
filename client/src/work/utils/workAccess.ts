import type { WorkAccessLevel } from '../api/workPermissions'

export type WorkAccessSource =
  | 'platform_admin'
  | 'explicit'
  | 'company_owner'
  | 'client_default'
  | 'employee_default'
  | 'external_default'

export type GrantableWorkAccessLevel = Exclude<WorkAccessLevel, 'guest'>

export const ACCESS_LEVELS: GrantableWorkAccessLevel[] = ['member', 'reviewer', 'operator', 'admin']

export const ACCESS_LEVEL_COPY: Record<WorkAccessLevel, {
  label: string
  short: string
  description: string
  bullets: string[]
}> = {
  guest: {
    label: 'Guest',
    short: 'Can collaborate, not operate Huume',
    description: 'Limited access for someone outside the company or without a grant.',
    bullets: ['No sensitive Huume reads', 'Cannot stage or execute actions'],
  },
  member: {
    label: 'Member',
    short: 'Can prepare work',
    description: 'A safe default for employees who need to work with the team.',
    bullets: ['Can stage Huume actions', 'Cannot approve or execute writes'],
  },
  reviewer: {
    label: 'Reviewer',
    short: 'Can inspect sensitive work',
    description: 'For HR, risk, or compliance leads who need visibility without write authority.',
    bullets: ['Can use sensitive Huume read tools', 'Cannot approve or execute writes'],
  },
  operator: {
    label: 'Operator',
    short: 'Can run approved work',
    description: 'For trusted managers who should confirm and execute Huume actions.',
    bullets: ['Can stage and approve actions', 'Can execute approved Huume work'],
  },
  admin: {
    label: 'Admin',
    short: 'Full workspace control',
    description: 'Full Work authority, including permission management.',
    bullets: ['All Huume and Ops capabilities', 'Can manage workspace access'],
  },
}

export function sourceLabel(source?: string): string {
  switch (source) {
    case 'platform_admin': return 'Platform admin'
    case 'company_owner': return 'Company owner'
    case 'client_default': return 'Default: company client'
    case 'employee_default': return 'Default: company employee'
    case 'explicit': return 'Custom grant'
    case 'external_default': return 'Default: external collaborator'
    default: return 'Default access'
  }
}

export function canManageWorkPermissions(capabilities?: string[]): boolean {
  return Boolean(capabilities?.includes('permissions.manage'))
}
