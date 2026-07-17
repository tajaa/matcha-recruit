import { matchPath } from 'react-router-dom'

// Authored per-page help cards for the floating HelpAssistant widget
// (components/help/HelpAssistant.tsx, mounted in layouts/AppLayout.tsx).
// A page only shows the widget if it has an entry here — adding coverage for
// a new tab means adding one entry, nothing else.
//
// ORDER IS LOAD-BEARING: entries are scanned first-match-wins, and the
// param route `ir/:incidentId` also matches `ir/osha` / `ir/risk-insights` /
// `ir/magic-links` — static IR entries MUST precede it.

export type PageHelp = {
  /** react-router path pattern relative to /app, e.g. 'ir/osha' */
  match: string
  title: string
  summary: string
  tips: string[]
  suggestions?: string[]
}

const PAGE_HELP: PageHelp[] = [
  // --- Incident Reporting ---
  {
    match: 'ir',
    title: 'Incidents',
    summary:
      'Your workplace incident log. Report new incidents, track their status from first report through investigation to closure, and export your data.',
    tips: [
      'Click "Report Incident" to log a new incident — you\'ll be taken straight into it afterwards.',
      'Switch between the Dashboard tab (trends and charts) and the Incidents tab (the working list).',
      'Search by title or incident number, and filter by status, type, or severity to find specific cases.',
      'Click any row to open the incident\'s detail page, where the AI Copilot guides next steps.',
      'Use Export to download your incident data.',
    ],
    suggestions: ['How do I report a new incident?', 'What do the status badges mean?', 'How do I find an old incident?'],
  },
  {
    match: 'ir/risk-insights',
    title: 'Risk Insights',
    summary:
      'AI-generated analytics over your incident history: risk scores, trends, recurring themes, and workers\'-comp impact.',
    tips: [
      'Filter everything by location and time window (30–180 days); hit Regenerate to force a fresh AI analysis.',
      'Overview shows your risk score, a severity × likelihood heatmap, trend charts, and risk dimensions.',
      'The Workers\' Comp section estimates premium impact and shows per-site TRIR/DART scorecards.',
      'Themes & People surfaces recurring incident themes (needs at least 3 supporting incidents) and repeat-involved people.',
    ],
    suggestions: ['What is TRIR?', 'How are themes detected?', 'What does the risk score mean?'],
  },
  {
    match: 'ir/magic-links',
    title: 'Magic Links',
    summary:
      'Anonymous and location-specific reporting links your employees can use without logging in — plus printable QR posters.',
    tips: [
      'Generate a company-wide anonymous link anyone can use to report with no name attached.',
      'Create location-specific links that lock the intake form to a site; add optional use limits or expiry.',
      'Download a branded QR poster PDF for any link — customize the poster colors with a live preview.',
      'Regenerate (rotate) a link if it leaks, or revoke it entirely; rotation history is kept per link.',
    ],
    suggestions: ['How do anonymous reports work?', 'How do I print a QR poster?', 'What happens if a link leaks?'],
  },
  {
    match: 'ir/osha',
    title: 'OSHA Logs',
    summary:
      'Your OSHA 300 log, 301 cases, and 300A annual summary — built automatically from recordable incidents, with exports and direct electronic filing to OSHA.',
    tips: [
      'Pick the year and establishment at the top to scope the log and summary.',
      'The 300 Log lists recordable cases — click a row to open the underlying incident. Privacy-case names are masked (reveals are audit-logged).',
      'Fill in the 300A summary fields (annual hours, employee counts, certification) and Save before exporting.',
      'Export the 300 Log CSV, 300A CSV, or Form 300A PDF — each export asks you to attest you\'ve reviewed it first.',
      'Use OSHA ITA filing to submit your 300A electronically: save your ITA API token, fix any flagged establishment fields, then Submit to OSHA.',
    ],
    suggestions: ['What counts as recordable?', 'How do I file my 300A electronically?', 'Why are some names masked?'],
  },
  {
    match: 'ir/people/:personId',
    title: 'Person History',
    summary:
      'A read-only view of one person\'s incident history: every incident they appear in and the role they played.',
    tips: [
      'The role chips show how often this person appears as injured party, witness, or reporter.',
      'Click any incident in the list to open its detail page.',
    ],
  },
  {
    match: 'ir/:incidentId',
    title: 'Incident Detail',
    summary:
      'Everything about one incident: the AI Copilot that guides your response, the full record, documents, and AI analysis.',
    tips: [
      'The Copilot tab streams step-by-step guidance and proposes action cards (set severity, OSHA classification, close the incident) you Accept or Skip.',
      'Use "Request more info" in Copilot to email the reporter or a witness a magic-link questionnaire — track, resend, or revoke requests there too.',
      'The Overview tab holds the full record: description, witnesses, people involved, root cause, and corrective actions (CAPA).',
      'Upload evidence under Documents; change Status and Severity from the sidebar.',
      'Export a PDF of the incident or a claims-readiness packet from the header actions.',
    ],
    suggestions: ['How do I close this incident?', 'How do I ask the reporter a follow-up question?', 'What is a corrective action?'],
  },

  // --- Compliance ---
  {
    match: 'compliance-calendar',
    title: 'Compliance Calendar',
    summary:
      'All your compliance deadlines in one place — overdue, due soon, and future — as a list or a month calendar.',
    tips: [
      'Switch between List view (grouped by Overdue / Due in 30 days / Due in 90 days / Future) and Month view.',
      'Filter by location and category — filters persist in the URL so you can bookmark a view.',
      'Click a row to mark it read; View opens the full alert in Compliance; Dismiss removes it.',
      'Baseline rows are universal federal/state annual deadlines and can\'t be dismissed.',
      'If the calendar is empty, run a compliance check on a location to populate deadlines.',
    ],
    suggestions: ['Where do these deadlines come from?', 'What are baseline deadlines?'],
  },
  {
    match: 'compliance',
    title: 'Compliance',
    summary:
      'Your jurisdiction-aware compliance hub: per-location requirements, alerts, upcoming legislation, and compliance checks.',
    tips: [
      'Add your business locations first — requirements and alerts are computed per location.',
      'Run a Compliance Check on a location to scan current law and generate requirements and alerts.',
      'Browse and pin requirements under the Requirements tab; handle Alerts by marking read, dismissing, or setting an action plan.',
      'The Upcoming tab tracks pending legislation that may affect you; History logs past checks.',
      'Use the Ask box at the top for regulatory questions — answers cite your actual requirements.',
    ],
    suggestions: ['How do I run a compliance check?', 'What does pinning a requirement do?', 'How do alerts work?'],
  },
  {
    match: 'matcha-x/compliance',
    title: 'Compliance',
    summary:
      'A read-only view of the compliance baseline built during your onboarding: per-location requirements and upcoming legislation. Live checks, alerts, and AI tools are part of the full Compliance product.',
    tips: [
      'The Requirements tab shows the jurisdictional requirements identified for your work locations during onboarding.',
      'The Upcoming tab tracks pending legislation that may affect you.',
      'Locked tabs (Alerts, Posters, and more) are part of the full Compliance upgrade.',
    ],
    suggestions: ['What are these requirements based on?', 'What do I get if I upgrade?'],
  },
  {
    match: 'workforce-compliance',
    title: 'Workforce Compliance',
    summary:
      'Four employment-practices controls you track for your own compliance — pay transparency, AI hiring-tool audits, biometric consent, and pay-equity studies. Keeping them current also strengthens the EPL (employment-practices liability) insurance profile your broker submits.',
    tips: [
      'Pay-equity studies: "Run analysis from payroll" computes a within-role pay screen from your roster; when employee demographics are on file (via HRIS), it also measures a real protected-class pay gap. Or log an external audit under "Log study".',
      'The gap panel compares median pay between genders within each role. Groups under 5 people in a role are excluded — too few to compare, and small enough to identify someone.',
      'A pay gap and pay dispersion are different: the gap is a difference between protected classes; dispersion is spread within a role that seniority can explain. Both are shown, separately.',
      'Pay transparency: mark each state in your footprint compliant once your job postings include salary ranges.',
      'AI hiring-tool audits and biometric consent: register each tool / collection point and keep its audit or consent current — "Suggest tools" / "Suggest points" proposes likely ones from your setup to start from.',
    ],
    suggestions: [
      'What is a protected-class pay gap and how is it measured?',
      'Why does a role show no gap even though it has men and women?',
      'How does keeping these current help my insurance?',
    ],
  },
]

/** Resolve the help card for the current pathname (first match wins). */
export function resolvePageHelp(pathname: string): PageHelp | null {
  for (const entry of PAGE_HELP) {
    if (matchPath({ path: `/app/${entry.match}`, end: true }, pathname)) return entry
  }
  return null
}
