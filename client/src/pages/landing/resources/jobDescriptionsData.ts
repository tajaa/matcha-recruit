export type Industry =
  | 'Hospitality'
  | 'Healthcare'
  | 'Retail'
  | 'Restaurants & QSR'
  | 'Construction & Trades'
  | 'Manufacturing & Warehouse'
  | 'Corporate & Professional'
  | 'Tech & Engineering'
  | 'Sales & Marketing'

export type JobDescription = {
  slug: string
  title: string
  industry: Industry
  description: string
}

export const INDUSTRIES: Industry[] = [
  'Hospitality',
  'Healthcare',
  'Retail',
  'Restaurants & QSR',
  'Construction & Trades',
  'Manufacturing & Warehouse',
  'Corporate & Professional',
  'Tech & Engineering',
  'Sales & Marketing',
]

export const JOB_DESCRIPTIONS: JobDescription[] = [
  // Hospitality
  { slug: 'front-desk-agent', title: 'Front Desk Agent', industry: 'Hospitality', description: 'Guest check-in/out, reservations, concierge basics, PMS proficiency.' },
  { slug: 'housekeeper', title: 'Housekeeper', industry: 'Hospitality', description: 'Room turnover, linen + amenity standards, lost-and-found protocol.' },
  { slug: 'housekeeping-supervisor', title: 'Housekeeping Supervisor', industry: 'Hospitality', description: 'Schedules + audits, training, inventory of room supplies.' },
  { slug: 'concierge', title: 'Concierge', industry: 'Hospitality', description: 'Reservations, transportation, local expertise, VIP service.' },
  { slug: 'event-coordinator', title: 'Event Coordinator', industry: 'Hospitality', description: 'BEO management, vendor coordination, on-site execution.' },

  // Healthcare
  { slug: 'registered-nurse', title: 'Registered Nurse', industry: 'Healthcare', description: 'Patient assessment, medication administration, care planning, documentation.' },
  { slug: 'lvn-lpn', title: 'LVN / LPN', industry: 'Healthcare', description: 'Vital signs, medication, wound care, RN-supervised duties.' },
  { slug: 'medical-assistant', title: 'Medical Assistant', industry: 'Healthcare', description: 'Rooming, EMR documentation, phlebotomy, clinical + clerical support.' },
  { slug: 'cna', title: 'Certified Nursing Assistant (CNA)', industry: 'Healthcare', description: 'ADLs, vitals, repositioning, documentation, infection control.' },
  { slug: 'phlebotomist', title: 'Phlebotomist', industry: 'Healthcare', description: 'Specimen collection, labeling, processing, patient interaction.' },
  { slug: 'medical-receptionist', title: 'Medical Receptionist', industry: 'Healthcare', description: 'Front-desk, scheduling, insurance verification, HIPAA-compliant intake.' },
  { slug: 'behavioral-health-technician', title: 'Behavioral Health Technician', industry: 'Healthcare', description: 'Patient observation, milieu management, documentation, de-escalation.' },
  { slug: 'home-health-aide', title: 'Home Health Aide', industry: 'Healthcare', description: 'In-home ADL support, light housekeeping, companionship, basic vitals.' },

  // Retail
  { slug: 'retail-sales-associate', title: 'Retail Sales Associate', industry: 'Retail', description: 'Customer service, POS, merchandising, loss-prevention awareness.' },
  { slug: 'cashier', title: 'Cashier', industry: 'Retail', description: 'POS, cash handling, customer service, basic returns + exchanges.' },
  { slug: 'store-manager', title: 'Store Manager', industry: 'Retail', description: 'P&L responsibility, scheduling, hiring, performance management.' },
  { slug: 'assistant-store-manager', title: 'Assistant Store Manager', industry: 'Retail', description: 'Shift leadership, opening/closing, training, KPI tracking.' },
  { slug: 'visual-merchandiser', title: 'Visual Merchandiser', industry: 'Retail', description: 'Window + floor displays, brand standards, planogram execution.' },
  { slug: 'stock-associate', title: 'Stock Associate', industry: 'Retail', description: 'Receiving, replenishment, back-of-house organization, inventory accuracy.' },

  // Restaurants & QSR
  { slug: 'line-cook', title: 'Line Cook', industry: 'Restaurants & QSR', description: 'Station management, prep, food safety (ServSafe), pace under pressure.' },
  { slug: 'prep-cook', title: 'Prep Cook', industry: 'Restaurants & QSR', description: 'Knife skills, recipe execution, sanitation, FIFO inventory.' },
  { slug: 'server', title: 'Server', industry: 'Restaurants & QSR', description: 'Order taking, POS, allergen awareness, upselling, table turnover.' },
  { slug: 'bartender', title: 'Bartender', industry: 'Restaurants & QSR', description: 'Cocktail preparation, responsible alcohol service, inventory + waste tracking.' },
  { slug: 'host', title: 'Host / Hostess', industry: 'Restaurants & QSR', description: 'Reservations, seating, wait management, guest communication.' },
  { slug: 'dishwasher', title: 'Dishwasher', industry: 'Restaurants & QSR', description: 'High-volume dishwashing, sanitation, basic kitchen support.' },
  { slug: 'shift-leader', title: 'Shift Leader', industry: 'Restaurants & QSR', description: 'Floor leadership, cash handling, opening/closing, food safety oversight.' },
  { slug: 'general-manager-restaurant', title: 'Restaurant General Manager', industry: 'Restaurants & QSR', description: 'P&L, food + labor cost management, hiring, brand standards.' },
  { slug: 'delivery-driver', title: 'Delivery Driver', industry: 'Restaurants & QSR', description: 'Routing, customer service, vehicle maintenance, food-safe handling.' },

  // Construction & Trades
  { slug: 'electrician', title: 'Electrician', industry: 'Construction & Trades', description: 'Wiring, code compliance (NEC), troubleshooting, blueprint reading.' },
  { slug: 'plumber', title: 'Plumber', industry: 'Construction & Trades', description: 'Installation, repair, code compliance, customer interaction.' },
  { slug: 'hvac-technician', title: 'HVAC Technician', industry: 'Construction & Trades', description: 'Install, service, refrigerant handling (EPA 608), diagnostics.' },
  { slug: 'carpenter', title: 'Carpenter', industry: 'Construction & Trades', description: 'Framing, finish work, blueprint reading, power tools, OSHA 10/30.' },
  { slug: 'project-superintendent', title: 'Project Superintendent', industry: 'Construction & Trades', description: 'Site supervision, subcontractor coordination, schedule, safety compliance.' },
  { slug: 'safety-officer', title: 'Safety Officer', industry: 'Construction & Trades', description: 'OSHA compliance, JSAs, incident investigation, training.' },

  // Manufacturing & Warehouse
  { slug: 'production-operator', title: 'Production Operator', industry: 'Manufacturing & Warehouse', description: 'Equipment operation, quality checks, lean basics, safety standards.' },
  { slug: 'forklift-operator', title: 'Forklift Operator', industry: 'Manufacturing & Warehouse', description: 'OSHA-certified material handling, inventory accuracy, safety inspections.' },
  { slug: 'warehouse-associate', title: 'Warehouse Associate', industry: 'Manufacturing & Warehouse', description: 'Picking + packing, RF scanning, receiving, putaway.' },
  { slug: 'shipping-receiving-clerk', title: 'Shipping & Receiving Clerk', industry: 'Manufacturing & Warehouse', description: 'BOL processing, carrier coordination, inventory transactions.' },
  { slug: 'maintenance-technician', title: 'Maintenance Technician', industry: 'Manufacturing & Warehouse', description: 'Preventive + reactive maintenance, electrical + mechanical troubleshooting.' },
  { slug: 'quality-inspector', title: 'Quality Inspector', industry: 'Manufacturing & Warehouse', description: 'Inspection, calipers + gauges, ISO documentation, NCR write-up.' },

  // Corporate & Professional
  { slug: 'hr-generalist', title: 'HR Generalist', industry: 'Corporate & Professional', description: 'Employee relations, benefits, onboarding, compliance, HRIS administration.' },
  { slug: 'hr-business-partner', title: 'HR Business Partner', industry: 'Corporate & Professional', description: 'Strategic partnership with leadership, talent planning, change management.' },
  { slug: 'recruiter', title: 'Recruiter', industry: 'Corporate & Professional', description: 'Sourcing, screening, ATS management, hiring-manager partnership.' },
  { slug: 'office-manager', title: 'Office Manager', industry: 'Corporate & Professional', description: 'Facilities, vendor management, AP support, executive admin.' },
  { slug: 'executive-assistant', title: 'Executive Assistant', industry: 'Corporate & Professional', description: 'Calendar + travel management, board prep, confidential project support.' },
  { slug: 'accountant', title: 'Accountant', industry: 'Corporate & Professional', description: 'GL maintenance, month-end close, reconciliations, audit support.' },
  { slug: 'bookkeeper', title: 'Bookkeeper', industry: 'Corporate & Professional', description: 'AP/AR, bank recs, payroll support, QuickBooks proficiency.' },
  { slug: 'payroll-specialist', title: 'Payroll Specialist', industry: 'Corporate & Professional', description: 'Multi-state payroll, tax filings, garnishments, compliance reporting.' },
  { slug: 'paralegal', title: 'Paralegal', industry: 'Corporate & Professional', description: 'Legal research, document drafting, e-filing, case management.' },

  // Tech & Engineering
  { slug: 'software-engineer', title: 'Software Engineer', industry: 'Tech & Engineering', description: 'Full-stack development, code review, on-call, modern web stack.' },
  { slug: 'senior-software-engineer', title: 'Senior Software Engineer', industry: 'Tech & Engineering', description: 'System design, mentorship, architecture decisions, cross-team partnership.' },
  { slug: 'product-manager', title: 'Product Manager', industry: 'Tech & Engineering', description: 'Roadmap, discovery, requirements, go-to-market partnership.' },
  { slug: 'designer', title: 'Product Designer', industry: 'Tech & Engineering', description: 'UX research, interaction design, design systems, prototyping.' },
  { slug: 'devops-engineer', title: 'DevOps / SRE Engineer', industry: 'Tech & Engineering', description: 'Infrastructure-as-code, observability, on-call, deploy pipelines.' },
  { slug: 'data-analyst', title: 'Data Analyst', industry: 'Tech & Engineering', description: 'SQL, dashboarding, A/B test analysis, stakeholder partnership.' },
  { slug: 'it-support-specialist', title: 'IT Support Specialist', industry: 'Tech & Engineering', description: 'Tier-1/2 support, MDM, identity provisioning, SaaS administration.' },

  // Sales & Marketing
  { slug: 'account-executive', title: 'Account Executive', industry: 'Sales & Marketing', description: 'Full-cycle sales, quota carry, CRM hygiene, MEDDIC / SPICED qualification.' },
  { slug: 'sdr', title: 'Sales Development Representative', industry: 'Sales & Marketing', description: 'Outbound prospecting, sequence management, qualification, hand-off.' },
  { slug: 'customer-success-manager', title: 'Customer Success Manager', industry: 'Sales & Marketing', description: 'Onboarding, expansion, retention, QBRs, customer health.' },
  { slug: 'marketing-manager', title: 'Marketing Manager', industry: 'Sales & Marketing', description: 'Campaigns, channel management, content calendar, brand stewardship.' },
  { slug: 'content-marketer', title: 'Content Marketer', industry: 'Sales & Marketing', description: 'Blog, email, SEO, social, distribution + measurement.' },
  { slug: 'social-media-manager', title: 'Social Media Manager', industry: 'Sales & Marketing', description: 'Channel strategy, calendar, community management, paid social basics.' },
]
