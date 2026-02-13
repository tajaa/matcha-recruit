import type { WalkthroughConfig } from '../types';

export const irListWalkthrough: WalkthroughConfig = {
  id: 'ir-list',
  title: 'Incident Management',
  category: 'admin',
  steps: [
    {
      target: 'ir-list-stats',
      title: 'Incident Overview',
      content: 'These cards show your open count, action-required items, critical incidents, and 30-day trends.',
      placement: 'bottom',
      expect: 'You should see four stat cards with numbers.',
      ifMissing: 'If these show dashes, the data is still loading. Wait a moment and try again.',
    },
    {
      target: 'ir-list-tabs',
      title: 'Status Filters',
      content: 'Filter incidents by status. "Needs Attention" surfaces items requiring immediate action.',
      placement: 'bottom',
      action: 'Click any tab to filter the list below.',
    },
    {
      target: 'ir-list-type-filter',
      title: 'Type Filter',
      content: 'Narrow incidents by type — safety, behavioral, property, near-miss, or other.',
      placement: 'bottom',
      action: 'Select a type from the dropdown to filter.',
    },
    {
      target: 'ir-list-severity-filter',
      title: 'Severity Filter',
      content: 'Filter by severity level to focus on critical or high-priority incidents.',
      placement: 'bottom',
      action: 'Select a severity level to filter.',
    },
    {
      target: 'ir-list-search',
      title: 'Search Incidents',
      content: 'Search by title, description, or incident number to quickly find specific records.',
      placement: 'bottom',
      action: 'Type a keyword and the list updates in real-time.',
    },
    {
      target: 'ir-list-analytics-btn',
      title: 'Analytics Dashboard',
      content: 'Switch to the visual analytics view for trends, charts, and location breakdowns.',
      placement: 'bottom',
      action: 'Click to open the analytics dashboard.',
    },
    {
      target: 'ir-list-report-btn',
      title: 'Report New Incident',
      content: 'Create a new incident report with full details, witnesses, and category-specific fields.',
      placement: 'bottom',
      action: 'Click to open the incident creation form.',
    },
    {
      target: 'ir-list-rows',
      title: 'Incident List',
      content: 'Each row shows the incident title, type, status, and date. Click any row for full details.',
      placement: 'top',
      action: 'Click an incident row to view its detail page.',
      expect: 'You should see rows with severity dots, titles, and status labels.',
      ifMissing: 'If no rows appear, there are no incidents matching your current filters.',
    },
    {
      target: 'ir-list-status-dropdown',
      title: 'Quick Status Update',
      content: 'Change an incident status directly from the list without opening the detail page.',
      placement: 'left',
      action: 'Select a new status from the dropdown to update.',
      ifMissing: 'This appears on each incident row. If missing, the list may be empty.',
    },
  ],
};

export const irDashboardWalkthrough: WalkthroughConfig = {
  id: 'ir-dashboard',
  title: 'Incident Analytics',
  category: 'admin',
  steps: [
    {
      target: 'ir-dash-stats',
      title: 'Key Metrics',
      content: 'At-a-glance numbers for total incidents, recent activity, open cases, and average resolution time.',
      placement: 'bottom',
      expect: 'You should see four stat cards with numbers.',
      ifMissing: 'Stats are loading. If they remain empty, there may be no incident data yet.',
    },
    {
      target: 'ir-dash-trend',
      title: 'Weekly Trend Chart',
      content: 'A bar chart showing incident volume over time. Hover any bar to see the exact count and date.',
      placement: 'bottom',
      action: 'Hover over bars to see weekly counts.',
      ifMissing: 'The chart appears when there is at least one incident in the last 90 days.',
    },
    {
      target: 'ir-dash-by-type',
      title: 'Incidents by Type',
      content: 'Breakdown of incidents by category — safety, behavioral, property, and near-miss.',
      placement: 'bottom',
      expect: 'A list of types with incident counts.',
    },
    {
      target: 'ir-dash-by-severity',
      title: 'Incidents by Severity',
      content: 'Distribution across critical, high, medium, and low severity levels.',
      placement: 'bottom',
      expect: 'Colored severity dots with counts.',
    },
    {
      target: 'ir-dash-hotspots',
      title: 'Location Hotspots',
      content: 'Top locations by incident frequency. Useful for identifying site-specific problems.',
      placement: 'bottom',
      expect: 'Location names with incident counts.',
      ifMissing: 'Hotspots appear when incidents have location data.',
    },
    {
      target: 'ir-dash-recent',
      title: 'Recent Incidents',
      content: 'The five most recently reported incidents. Click any row to open the detail page.',
      placement: 'top',
      action: 'Click a row to view the full incident.',
    },
  ],
};

export const irCreateWalkthrough: WalkthroughConfig = {
  id: 'ir-create',
  title: 'Report an Incident',
  category: 'admin',
  steps: [
    {
      target: 'ir-create-type',
      title: 'Incident Type',
      content: 'Select the category that best describes the incident. This determines which additional fields appear.',
      placement: 'bottom',
      action: 'Click a type button to select it.',
      expect: 'The selected type is highlighted in white.',
    },
    {
      target: 'ir-create-severity',
      title: 'Severity Level',
      content: 'Set the severity using the colored dots — green (low) through red (critical).',
      placement: 'bottom',
      action: 'Click a dot to select the severity level.',
      expect: 'The selected dot has a white ring around it.',
    },
    {
      target: 'ir-create-title',
      title: 'Incident Title',
      content: 'Enter a brief description of what happened. This is the main identifier in the incident list.',
      placement: 'bottom',
      action: 'Type a concise summary of the incident.',
    },
    {
      target: 'ir-create-when',
      title: 'Date & Time',
      content: 'Record when the incident occurred. This is required for compliance tracking.',
      placement: 'bottom',
      action: 'Select the date and time of the incident.',
    },
    {
      target: 'ir-create-where',
      title: 'Location',
      content: 'Specify where the incident happened — a specific area, room, or site name.',
      placement: 'bottom',
      action: 'Type the location or select a business location below.',
    },
    {
      target: 'ir-create-witnesses',
      title: 'Witnesses',
      content: 'Add witness names and contact info. This is optional but helps with investigations.',
      placement: 'top',
      action: 'Click "+ Add" to add a witness entry.',
    },
    {
      target: 'ir-create-submit',
      title: 'Submit Report',
      content: 'When all required fields are filled, submit the report. AI analysis runs automatically after submission.',
      placement: 'top',
      action: 'Click Submit to create the incident report.',
      expect: 'You will be redirected to the new incident detail page.',
    },
  ],
};

export const irCategorizationWalkthrough: WalkthroughConfig = {
  id: 'ir-categorization',
  title: 'AI Categorization',
  category: 'admin',
  steps: [
    {
      target: 'ir-cat-type',
      title: 'Suggested Type',
      content: 'The AI-suggested incident type based on the description and context.',
      placement: 'bottom',
      expect: 'A colored badge showing the suggested category.',
    },
    {
      target: 'ir-cat-confidence',
      title: 'Confidence Score',
      content: 'How confident the AI is in its suggestion. Higher scores mean stronger signal.',
      placement: 'bottom',
      expect: 'A progress bar with a percentage value.',
    },
    {
      target: 'ir-cat-reasoning',
      title: 'AI Reasoning',
      content: 'The AI explains why it chose this category. Review this to decide whether to accept.',
      placement: 'bottom',
      expect: 'A text explanation of the categorization logic.',
    },
    {
      target: 'ir-cat-meta',
      title: 'Analysis Metadata',
      content: 'Shows when the analysis was generated and whether it came from cache.',
      placement: 'top',
      expect: 'A timestamp and optional cache indicator.',
    },
  ],
};

export const irSeverityWalkthrough: WalkthroughConfig = {
  id: 'ir-severity',
  title: 'AI Severity Assessment',
  category: 'admin',
  steps: [
    {
      target: 'ir-sev-badge',
      title: 'Suggested Severity',
      content: 'The AI-recommended severity level based on injury potential, regulatory exposure, and impact.',
      placement: 'bottom',
      expect: 'A colored severity badge (critical, high, medium, or low).',
    },
    {
      target: 'ir-sev-factors',
      title: 'Contributing Factors',
      content: 'The specific factors the AI considered when determining severity.',
      placement: 'bottom',
      expect: 'A bulleted list of factors.',
      ifMissing: 'Factors may be empty if the AI had limited information.',
    },
    {
      target: 'ir-sev-reasoning',
      title: 'Detailed Reasoning',
      content: 'Full explanation of how the AI arrived at this severity level.',
      placement: 'top',
      expect: 'A text explanation of the severity assessment.',
    },
  ],
};

export const irRootCauseWalkthrough: WalkthroughConfig = {
  id: 'ir-root-cause',
  title: 'Root Cause Analysis',
  category: 'admin',
  steps: [
    {
      target: 'ir-rc-cause',
      title: 'Primary Cause',
      content: 'The main root cause identified by the AI after analyzing the incident details.',
      placement: 'bottom',
      expect: 'A highlighted text block with the primary cause.',
    },
    {
      target: 'ir-rc-factors',
      title: 'Contributing Factors',
      content: 'Additional factors that contributed to the incident beyond the primary cause.',
      placement: 'bottom',
      expect: 'A bulleted list of contributing factors.',
      ifMissing: 'Factors may be empty for simpler incidents.',
    },
    {
      target: 'ir-rc-prevention',
      title: 'Prevention Suggestions',
      content: 'AI-generated recommendations to prevent similar incidents in the future.',
      placement: 'bottom',
      expect: 'A list of actionable prevention steps.',
    },
    {
      target: 'ir-rc-analysis',
      title: 'Detailed Analysis',
      content: 'The full reasoning behind the root cause determination.',
      placement: 'top',
      expect: 'A detailed text explanation.',
    },
  ],
};

export const irRecommendationsWalkthrough: WalkthroughConfig = {
  id: 'ir-recommendations',
  title: 'AI Recommendations',
  category: 'admin',
  steps: [
    {
      target: 'ir-rec-summary',
      title: 'Summary',
      content: 'A high-level overview of the recommended corrective actions.',
      placement: 'bottom',
      expect: 'A brief text summary of recommendations.',
      ifMissing: 'Summary may not appear if the AI generated individual actions only.',
    },
    {
      target: 'ir-rec-cards',
      title: 'Action Cards',
      content: 'Each card is a specific corrective action with priority level, responsible party, and estimated effort.',
      placement: 'bottom',
      action: 'Review each card and note the priority badges.',
      expect: 'Cards with action descriptions, priority tags, and detail rows.',
    },
    {
      target: 'ir-rec-meta',
      title: 'Analysis Metadata',
      content: 'Shows when recommendations were generated and cache status.',
      placement: 'top',
      expect: 'A timestamp and optional cache indicator.',
    },
  ],
};

export const irSimilarWalkthrough: WalkthroughConfig = {
  id: 'ir-similar',
  title: 'Similar Incidents',
  category: 'admin',
  steps: [
    {
      target: 'ir-sim-pattern',
      title: 'Pattern Summary',
      content: 'AI-detected patterns across similar incidents. Highlights systemic issues worth investigating.',
      placement: 'bottom',
      expect: 'A text description of detected patterns.',
      ifMissing: 'Pattern summary may be empty if no strong patterns were detected.',
    },
    {
      target: 'ir-sim-cards',
      title: 'Similar Incident Cards',
      content: 'Each card shows a historically similar incident with a similarity score and common factors.',
      placement: 'bottom',
      action: 'Click an incident number to navigate to its detail page.',
      expect: 'Cards with incident IDs, similarity bars, and common factor lists.',
      ifMissing: 'No similar incidents found — this may be a unique event.',
    },
    {
      target: 'ir-sim-meta',
      title: 'Analysis Metadata',
      content: 'Shows when the similarity analysis was generated and cache status.',
      placement: 'top',
      expect: 'A timestamp and optional cache indicator.',
    },
  ],
};
