import { lazy, type ComponentType, type LazyExoticComponent } from 'react'

const CompensationAnimation = lazy(() =>
  import('./CompensationAnimation').then((m) => ({ default: m.CompensationAnimation })),
)
const RiskAssessmentAnimation = lazy(() =>
  import('./RiskAssessmentAnimation').then((m) => ({ default: m.RiskAssessmentAnimation })),
)
const InvestigationTimelineAnimation = lazy(() =>
  import('./InvestigationTimelineAnimation').then((m) => ({ default: m.InvestigationTimelineAnimation })),
)
const PreTerminationAnimation = lazy(() =>
  import('./PreTerminationAnimation').then((m) => ({ default: m.PreTerminationAnimation })),
)

export { CompensationAnimation, RiskAssessmentAnimation, InvestigationTimelineAnimation, PreTerminationAnimation }

export const ANIMATION_BY_SIZZLE_ID: Record<string, LazyExoticComponent<ComponentType>> = {
  hr: CompensationAnimation,
  grc: RiskAssessmentAnimation,
  er: InvestigationTimelineAnimation,
  termination: PreTerminationAnimation,
}
