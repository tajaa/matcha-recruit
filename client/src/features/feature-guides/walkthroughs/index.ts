import type { GuideKey, WalkthroughConfig } from '../types';
import {
  irListWalkthrough,
  irDashboardWalkthrough,
  irCreateWalkthrough,
  irCategorizationWalkthrough,
  irSeverityWalkthrough,
  irRootCauseWalkthrough,
  irRecommendationsWalkthrough,
  irSimilarWalkthrough,
} from './ir';
import {
  complianceWalkthrough,
  erCopilotWalkthrough,
  timeOffWalkthrough,
  employeesWalkthrough,
} from './admin';
import {
  portalOnboardingWalkthrough,
  portalDocumentsWalkthrough,
  portalPTOWalkthrough,
} from './portal';

export const WALKTHROUGH_CONFIGS: Record<GuideKey, WalkthroughConfig> = {
  'ir-list': irListWalkthrough,
  'ir-dashboard': irDashboardWalkthrough,
  'ir-create': irCreateWalkthrough,
  'ir-categorization': irCategorizationWalkthrough,
  'ir-severity': irSeverityWalkthrough,
  'ir-root-cause': irRootCauseWalkthrough,
  'ir-recommendations': irRecommendationsWalkthrough,
  'ir-similar': irSimilarWalkthrough,
  compliance: complianceWalkthrough,
  'er-copilot': erCopilotWalkthrough,
  'time-off': timeOffWalkthrough,
  employees: employeesWalkthrough,
  'portal-onboarding': portalOnboardingWalkthrough,
  'portal-documents': portalDocumentsWalkthrough,
  'portal-pto': portalPTOWalkthrough,
};
