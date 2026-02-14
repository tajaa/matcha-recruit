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
  policiesWalkthrough,
  offerLettersWalkthrough,
  erCopilotWalkthrough,
  timeOffWalkthrough,
  leaveManagementWalkthrough,
  accommodationsWalkthrough,
  employeesWalkthrough,
} from './admin';
import {
  portalOnboardingWalkthrough,
  portalDocumentsWalkthrough,
  portalPTOWalkthrough,
  portalLeaveWalkthrough,
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
  policies: policiesWalkthrough,
  'offer-letters': offerLettersWalkthrough,
  'er-copilot': erCopilotWalkthrough,
  'time-off': timeOffWalkthrough,
  'leave-management': leaveManagementWalkthrough,
  accommodations: accommodationsWalkthrough,
  employees: employeesWalkthrough,
  'portal-onboarding': portalOnboardingWalkthrough,
  'portal-documents': portalDocumentsWalkthrough,
  'portal-pto': portalPTOWalkthrough,
  'portal-leave': portalLeaveWalkthrough,
};
