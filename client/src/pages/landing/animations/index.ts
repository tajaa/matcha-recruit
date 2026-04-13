import type { ComponentType } from 'react'
import { CompensationAnimation } from './CompensationAnimation'
import { RiskAssessmentAnimation } from './RiskAssessmentAnimation'
import { InvestigationTimelineAnimation } from './InvestigationTimelineAnimation'
import { AIEvaluationAnimation } from './AIEvaluationAnimation'

export { CompensationAnimation, RiskAssessmentAnimation, InvestigationTimelineAnimation, AIEvaluationAnimation }

export const ANIMATION_BY_SIZZLE_ID: Record<string, ComponentType> = {
  hr: CompensationAnimation,
  grc: RiskAssessmentAnimation,
  er: InvestigationTimelineAnimation,
  ai: AIEvaluationAnimation,
}
