import type { JDContent } from './types'

export const administrative: Record<string, JDContent> = {
  'hr-generalist': {
    summary: 'The HR Generalist is a versatile HR professional who supports employees and managers across the full employment lifecycle. You will handle employee relations, benefits administration, onboarding, compliance, and HRIS maintenance — serving as a trusted advisor and operational resource for the business.',
    responsibilities: [
      'Manage the onboarding and offboarding process for all employees',
      'Administer employee benefits programs and serve as the primary employee contact for enrollment and claims issues',
      'Maintain accurate employee records in the HRIS and ensure data integrity',
      'Support employee relations by investigating complaints, documenting findings, and recommending resolutions',
      'Ensure compliance with federal, state, and local employment laws including I-9, EEO, FMLA, and ADA',
      'Assist managers with performance management, coaching, and corrective action documentation',
      'Develop and maintain HR policies and employee handbook content',
    ],
    requirements: [
      "Bachelor's degree in Human Resources, Business Administration, or related field",
      '3+ years of generalist HR experience',
      'Working knowledge of federal and state employment law',
      'Proficiency with HRIS platforms (Workday, BambooHR, ADP, or similar)',
      'Strong interpersonal skills and discretion in handling confidential information',
    ],
    preferred: [
      'SHRM-CP or PHR certification',
      'Experience in a multi-state workforce environment',
      'Familiarity with Applicant Tracking Systems (ATS)',
    ],
  },

  'hr-business-partner': {
    summary: 'The HR Business Partner (HRBP) serves as a strategic advisor to senior leaders and people managers, aligning HR initiatives with business objectives. You will lead talent planning, organizational effectiveness, change management, and complex employee relations — partnering deeply with assigned client groups to build high-performing teams.',
    responsibilities: [
      'Partner with senior leaders to develop and execute people strategies aligned with business goals',
      'Advise managers on organizational design, role clarity, and workforce planning',
      'Lead talent review and succession planning processes for assigned business units',
      'Manage complex employee relations matters including investigations and performance plans',
      'Drive change management initiatives including restructures, mergers, and culture programs',
      'Analyze HR data and metrics to identify trends and present actionable recommendations to leadership',
      'Collaborate with Centers of Excellence (Talent Acquisition, Total Rewards, L&D) to deliver integrated solutions',
    ],
    requirements: [
      "Bachelor's degree in HR, Business, or related field; Master's degree a plus",
      '5+ years of HR experience with at least 2 years as an HRBP or senior HR generalist',
      'Deep knowledge of employment law, organizational development, and talent management',
      'Proven ability to influence senior leaders and navigate organizational complexity',
      'Strong analytical and data visualization skills',
    ],
    preferred: [
      'SHRM-SCP or SPHR certification',
      'Experience supporting a business unit of 500+ employees',
      'Coaching certification or executive coaching experience',
    ],
  },

  'recruiter': {
    summary: 'The Recruiter manages full-cycle talent acquisition for assigned roles and business units. You will source candidates through diverse channels, conduct structured screening interviews, partner closely with hiring managers, and deliver an exceptional candidate experience from first touch through offer acceptance.',
    responsibilities: [
      'Partner with hiring managers to define role requirements, ideal candidate profiles, and sourcing strategies',
      'Post positions, source candidates via LinkedIn, job boards, referrals, and community channels',
      'Screen resumes and conduct phone or video screens to assess qualifications and cultural fit',
      'Manage candidates through the ATS, maintain pipeline hygiene, and provide consistent status updates',
      'Coordinate and facilitate structured interview processes with clear evaluation criteria',
      'Extend verbal and written offers; negotiate and close candidates effectively',
      'Track and report key recruiting metrics (time-to-fill, source-of-hire, offer acceptance rate)',
    ],
    requirements: [
      "Bachelor's degree or equivalent experience",
      '3+ years of in-house or agency recruiting experience',
      'Proficiency with ATS platforms (Greenhouse, Lever, iCIMS, or similar)',
      'Strong sourcing skills including Boolean search and LinkedIn Recruiter',
      'Excellent communication skills and a candidate-first mindset',
    ],
    preferred: [
      'PHR, SHRM-CP, or LinkedIn Recruiter certification',
      'Experience recruiting for technical or specialized roles',
      'Familiarity with structured interviewing and competency-based assessment frameworks',
    ],
  },

  'office-manager': {
    summary: 'The Office Manager ensures the office runs smoothly by managing facilities, vendors, supplies, and administrative operations. You will serve as the go-to resource for building logistics, support executive assistants and administrative staff, and maintain a productive, well-organized workplace.',
    responsibilities: [
      'Oversee daily office operations including facilities management, vendor relationships, and supply procurement',
      'Manage office lease, utilities, parking, and building security access',
      'Coordinate IT support and asset management in partnership with the IT team',
      'Maintain office budget, track expenses, and process invoices and expense reports',
      'Organize company events, all-hands meetings, catering, and employee engagement activities',
      'Support accounts payable and basic bookkeeping functions as needed',
      'Onboard new employees with office orientation, equipment provisioning, and access setup',
    ],
    requirements: [
      '3+ years of office management or senior administrative experience',
      'Strong organizational, prioritization, and multitasking skills',
      'Proficiency with Microsoft 365 or Google Workspace',
      'Excellent vendor negotiation and relationship-management skills',
      'Discretion in handling confidential company and personnel information',
    ],
    preferred: [
      "Associate's or Bachelor's degree in Business Administration",
      'Experience managing an office of 50+ employees',
      'Basic accounting knowledge (QuickBooks, NetSuite, or equivalent)',
    ],
  },

  'executive-assistant': {
    summary: 'The Executive Assistant provides high-level administrative support to one or more C-suite or senior executives. You will manage complex calendars, coordinate domestic and international travel, prepare board materials, and handle sensitive projects — acting as a trusted extension of the executive you support.',
    responsibilities: [
      'Manage complex and frequently changing executive calendars across multiple time zones',
      'Coordinate domestic and international travel including flights, hotels, ground transport, and itineraries',
      'Prepare and distribute board presentations, briefing documents, and meeting materials',
      "Screen and respond to correspondence on the executive's behalf as directed",
      'Process expense reports and reconcile corporate card statements on schedule',
      'Organize off-sites, leadership meetings, and team events end-to-end',
      'Handle confidential information with the highest level of discretion',
    ],
    requirements: [
      '5+ years of executive assistant or chief-of-staff experience supporting C-level leaders',
      'Expert proficiency with calendar tools, Microsoft 365, and Google Workspace',
      'Exceptional written and verbal communication skills',
      'Ability to anticipate needs, act proactively, and manage competing priorities',
      'Proven discretion with sensitive and confidential information',
    ],
    preferred: [
      'Experience supporting a CEO, CFO, or board-level committee',
      'Notary public certification',
      'Project management certification (PMP, CAPM, or equivalent)',
    ],
  },

  'accountant': {
    summary: 'The Accountant maintains the accuracy and integrity of financial records through the full accounting cycle. You will manage general ledger entries, support the month-end and year-end close, perform reconciliations, and provide clean, timely financial data to support management decision-making and audit readiness.',
    responsibilities: [
      'Record journal entries and maintain the general ledger for assigned accounts',
      'Perform month-end close activities including accruals, prepayments, and intercompany reconciliations',
      'Reconcile balance-sheet accounts and investigate variances',
      'Assist in preparation of financial statements, management reports, and board packages',
      'Support internal and external audit processes by providing documentation and analysis',
      'Maintain fixed-asset schedules and depreciation calculations',
      'Ensure compliance with GAAP and company accounting policies',
    ],
    requirements: [
      "Bachelor's degree in Accounting, Finance, or related field",
      '3+ years of accounting experience in a corporate or public accounting environment',
      'Proficiency with ERP accounting systems (SAP, NetSuite, QuickBooks, or similar)',
      'Strong Excel skills including pivot tables and VLOOKUP/XLOOKUP',
      'Knowledge of GAAP and solid analytical skills',
    ],
    preferred: [
      'CPA license or active CPA candidate',
      'Public accounting (Big 4 or regional firm) experience',
      'Experience with consolidations, multi-currency accounting, or ASC 606 revenue recognition',
    ],
  },

  'bookkeeper': {
    summary: 'The Bookkeeper maintains accurate day-to-day financial records for the organization. You will process accounts payable and receivable, reconcile bank and credit card statements, support payroll, and provide clean books that enable leadership to make informed business decisions.',
    responsibilities: [
      'Record daily financial transactions including sales, purchases, payments, and receipts',
      'Process vendor invoices and manage accounts payable payment run',
      'Invoice customers and follow up on outstanding receivables',
      'Reconcile bank, credit card, and petty cash accounts monthly',
      'Assist with payroll processing and tax payment remittances',
      'Prepare monthly financial reports and balance-sheet summaries for management',
      'Maintain organized, audit-ready financial documentation',
    ],
    requirements: [
      "High school diploma; Associate's degree in Accounting or Business preferred",
      '3+ years of bookkeeping experience',
      'QuickBooks Online or Desktop proficiency (certification a plus)',
      'Attention to accuracy and strong organizational skills',
      'Discretion in handling confidential financial data',
    ],
    preferred: [
      'QuickBooks ProAdvisor or similar certification',
      'Experience with Xero, FreshBooks, or Zoho Books',
      'Basic understanding of accrual accounting and payroll tax rules',
    ],
  },

  'payroll-specialist': {
    summary: 'The Payroll Specialist ensures employees across all states are paid accurately and on time, every pay period. You will manage the end-to-end payroll cycle, handle tax filings, process garnishments, and maintain rigorous records in compliance with federal, state, and local payroll regulations.',
    responsibilities: [
      'Process multi-state payroll for salaried, hourly, and variable-pay employees on scheduled pay dates',
      'Review timekeeping data for accuracy and resolve discrepancies before processing',
      'Calculate and withhold federal, state, and local income taxes, Social Security, and Medicare',
      'Process wage garnishments, child support orders, and tax levies per legal requirements',
      'Remit payroll tax deposits on schedule and file quarterly/annual returns (941, 940, W-2, etc.)',
      'Respond to employee payroll inquiries and resolve discrepancies promptly',
      'Maintain payroll audit trails and support internal and external audit requests',
    ],
    requirements: [
      '3+ years of full-cycle multi-state payroll processing experience',
      'Proficiency with payroll software (ADP, Paylocity, Paycom, or similar)',
      'Knowledge of federal and state wage, hour, and payroll tax regulations',
      'High degree of accuracy and confidentiality',
      'Strong analytical and problem-solving skills',
    ],
    preferred: [
      'Certified Payroll Professional (CPP) or FPC designation',
      'Experience processing payroll for 500+ employees',
      'Familiarity with HRIS integration and automated payroll feeds',
    ],
  },

  'paralegal': {
    summary: 'The Paralegal supports attorneys by conducting legal research, drafting documents, managing cases, and handling e-filings. You will own significant administrative and substantive workflow under attorney supervision, directly improving throughput and service quality for the practice or legal department.',
    responsibilities: [
      'Conduct legal research using Westlaw, LexisNexis, and public databases',
      'Draft pleadings, motions, contracts, correspondence, and other legal documents for attorney review',
      'Manage case files, deadlines, and dockets including court calendaring systems',
      'Prepare for depositions, hearings, and trials by organizing exhibits and witness materials',
      'Coordinate e-filing of documents with state and federal courts using required platforms',
      'Liaise with clients, courts, opposing counsel, and expert witnesses',
      'Summarize depositions, discovery documents, and medical records',
    ],
    requirements: [
      'Paralegal certificate from an ABA-approved program or Bachelor\'s degree in Paralegal Studies or related field',
      '2+ years of paralegal experience in a law firm or corporate legal department',
      'Proficiency with legal research databases (Westlaw, LexisNexis) and case management software',
      'Excellent writing, organizational, and deadline-management skills',
      'Understanding of court procedures and rules in applicable jurisdiction',
    ],
    preferred: [
      'NALA Certified Paralegal (CP) or NFPA CORE Registered Paralegal (RP) designation',
      'Specialization in litigation, corporate law, real estate, or employment law',
      'Experience with e-discovery platforms (Relativity, Everlaw)',
    ],
  },
}
