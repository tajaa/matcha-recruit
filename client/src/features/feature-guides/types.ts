export type Placement = 'top' | 'bottom' | 'left' | 'right';

export interface WalkthroughStep {
  target: string;         // data-tour attribute value → [data-tour="value"]
  title: string;          // Step heading
  content: string;        // Main instruction text
  placement: Placement;   // Tooltip position relative to target
  action?: string;        // "Click this to..." hint
  expect?: string;        // "You should see..."
  ifMissing?: string;     // "If this is missing, it means..."
}

export interface WalkthroughConfig {
  id: string;
  title: string;
  category: 'admin' | 'employee';
  steps: WalkthroughStep[];
}

export type GuideKey =
  | 'compliance'
  | 'ir-list'
  | 'ir-dashboard'
  | 'ir-create'
  | 'ir-categorization'
  | 'ir-severity'
  | 'ir-root-cause'
  | 'ir-recommendations'
  | 'ir-similar'
  | 'er-copilot'
  | 'time-off'
  | 'employees'
  | 'portal-onboarding'
  | 'portal-documents'
  | 'portal-pto';
