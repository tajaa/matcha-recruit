import { PLAN_REQUIRED_EVENT, type PlanRequiredDetail } from '../../api/client'

export function showPaywall(feature: string, requiredPlan: 'lite' | 'pro', currentPlan: PlanRequiredDetail['current_plan']) {
  window.dispatchEvent(new CustomEvent<PlanRequiredDetail>(PLAN_REQUIRED_EVENT, {
    detail: {
      code: 'plan_required',
      feature,
      required_plan: requiredPlan,
      current_plan: currentPlan,
    },
  }))
}
