/**
 * Typed wrappers for the master-admin onboarding wizard backend.
 *
 * Mirrors the 10 endpoints exposed at /api/admin/onboarding/*. Each
 * function returns the same shape the backend Pydantic models emit
 * (see server/app/core/models/admin_onboarding.py).
 */

import { dashboardApi } from './dashboard'
import { scopeApi } from './scope'
import { sessionsApi } from './sessions'

export * from './types'
export * from './urls'

export const adminOnboarding = {
  ...sessionsApi,
  ...dashboardApi,
  ...scopeApi,
}
