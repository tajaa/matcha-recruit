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
const AIEvaluationAnimation = lazy(() =>
  import('./AIEvaluationAnimation').then((m) => ({ default: m.AIEvaluationAnimation })),
)

export { CompensationAnimation, RiskAssessmentAnimation, InvestigationTimelineAnimation, AIEvaluationAnimation }

export const ANIMATION_BY_SIZZLE_ID: Record<string, LazyExoticComponent<ComponentType>> = {
  hr: CompensationAnimation,
  grc: RiskAssessmentAnimation,
  er: InvestigationTimelineAnimation,
  ai: AIEvaluationAnimation,
}
