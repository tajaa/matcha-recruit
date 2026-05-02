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
  downloadUrl?: string
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

const DL = 'https://d1ri804v59kjwh.cloudfront.net/resources/job-descriptions/'

export const JOB_DESCRIPTIONS: JobDescription[] = [
  // Hospitality
  { slug: 'front-desk-agent', title: 'Front Desk Agent', industry: 'Hospitality', description: 'Guest check-in/out, reservations, concierge basics, PMS proficiency.', downloadUrl: DL + 'd87a4300128c498990b75cbbc7265b4e.docx' },
  { slug: 'housekeeper', title: 'Housekeeper', industry: 'Hospitality', description: 'Room turnover, linen + amenity standards, lost-and-found protocol.', downloadUrl: DL + '63461675f74b401eb79d678b8ea69e4c.docx' },
  { slug: 'housekeeping-supervisor', title: 'Housekeeping Supervisor', industry: 'Hospitality', description: 'Schedules + audits, training, inventory of room supplies.', downloadUrl: DL + 'dfa894642145427cb6dcd2fdf61b780f.docx' },
  { slug: 'concierge', title: 'Concierge', industry: 'Hospitality', description: 'Reservations, transportation, local expertise, VIP service.', downloadUrl: DL + '461a260680ba42468e39ed6f557b7327.docx' },
  { slug: 'event-coordinator', title: 'Event Coordinator', industry: 'Hospitality', description: 'BEO management, vendor coordination, on-site execution.', downloadUrl: DL + 'fc5ce4171dee42f8b258e947888f5c4c.docx' },

  // Healthcare
  { slug: 'registered-nurse', title: 'Registered Nurse', industry: 'Healthcare', description: 'Patient assessment, medication administration, care planning, documentation.', downloadUrl: DL + 'cad048200ad243b48bd745845975c3ab.docx' },
  { slug: 'lvn-lpn', title: 'LVN / LPN', industry: 'Healthcare', description: 'Vital signs, medication, wound care, RN-supervised duties.', downloadUrl: DL + '7e4826d92e1742739f3ecbc7b3b30e69.docx' },
  { slug: 'medical-assistant', title: 'Medical Assistant', industry: 'Healthcare', description: 'Rooming, EMR documentation, phlebotomy, clinical + clerical support.', downloadUrl: DL + 'ae42866fa40847b78b780b5798a725b4.docx' },
  { slug: 'cna', title: 'Certified Nursing Assistant (CNA)', industry: 'Healthcare', description: 'ADLs, vitals, repositioning, documentation, infection control.', downloadUrl: DL + '88acff7f511a47ae9d69559674cffbcc.docx' },
  { slug: 'phlebotomist', title: 'Phlebotomist', industry: 'Healthcare', description: 'Specimen collection, labeling, processing, patient interaction.', downloadUrl: DL + 'd0af14c8a2e54cd1906f949e27f583e1.docx' },
  { slug: 'medical-receptionist', title: 'Medical Receptionist', industry: 'Healthcare', description: 'Front-desk, scheduling, insurance verification, HIPAA-compliant intake.', downloadUrl: DL + '11a195317b104b68b8a9eea87869e90c.docx' },
  { slug: 'behavioral-health-technician', title: 'Behavioral Health Technician', industry: 'Healthcare', description: 'Patient observation, milieu management, documentation, de-escalation.', downloadUrl: DL + '89a4265f8c0b4efb80c605b90c49ef14.docx' },
  { slug: 'home-health-aide', title: 'Home Health Aide', industry: 'Healthcare', description: 'In-home ADL support, light housekeeping, companionship, basic vitals.', downloadUrl: DL + '8a87a287bf84422386fb41ec48f78788.docx' },

  // Retail
  { slug: 'retail-sales-associate', title: 'Retail Sales Associate', industry: 'Retail', description: 'Customer service, POS, merchandising, loss-prevention awareness.', downloadUrl: DL + '409605a2ebc7465a961c7dd78843b472.docx' },
  { slug: 'cashier', title: 'Cashier', industry: 'Retail', description: 'POS, cash handling, customer service, basic returns + exchanges.', downloadUrl: DL + '28bb401d93364d558c2570f7c187d999.docx' },
  { slug: 'store-manager', title: 'Store Manager', industry: 'Retail', description: 'P&L responsibility, scheduling, hiring, performance management.', downloadUrl: DL + '2dbbdf576a2843149039a0b3ec57bbe0.docx' },
  { slug: 'assistant-store-manager', title: 'Assistant Store Manager', industry: 'Retail', description: 'Shift leadership, opening/closing, training, KPI tracking.', downloadUrl: DL + '371e62000abc4e489263543288b4aea0.docx' },
  { slug: 'visual-merchandiser', title: 'Visual Merchandiser', industry: 'Retail', description: 'Window + floor displays, brand standards, planogram execution.', downloadUrl: DL + '900ce975b4aa4b63821737e870d0241e.docx' },
  { slug: 'stock-associate', title: 'Stock Associate', industry: 'Retail', description: 'Receiving, replenishment, back-of-house organization, inventory accuracy.', downloadUrl: DL + '689419beeb784319b657df9d5ed6d7dd.docx' },

  // Restaurants & QSR
  { slug: 'line-cook', title: 'Line Cook', industry: 'Restaurants & QSR', description: 'Station management, prep, food safety (ServSafe), pace under pressure.', downloadUrl: DL + '1c2f7b039de04b109e89c9d3f368f309.docx' },
  { slug: 'prep-cook', title: 'Prep Cook', industry: 'Restaurants & QSR', description: 'Knife skills, recipe execution, sanitation, FIFO inventory.', downloadUrl: DL + '9f40ef998a9b40e7b1564513bc4c6153.docx' },
  { slug: 'server', title: 'Server', industry: 'Restaurants & QSR', description: 'Order taking, POS, allergen awareness, upselling, table turnover.', downloadUrl: DL + '642acce8f1c04270aba5524b0e820d06.docx' },
  { slug: 'bartender', title: 'Bartender', industry: 'Restaurants & QSR', description: 'Cocktail preparation, responsible alcohol service, inventory + waste tracking.', downloadUrl: DL + 'b84014b7e7f84bcb993745c5a26b5ce5.docx' },
  { slug: 'host', title: 'Host / Hostess', industry: 'Restaurants & QSR', description: 'Reservations, seating, wait management, guest communication.', downloadUrl: DL + 'c460703dbd3d43188671efb894330afb.docx' },
  { slug: 'dishwasher', title: 'Dishwasher', industry: 'Restaurants & QSR', description: 'High-volume dishwashing, sanitation, basic kitchen support.', downloadUrl: DL + 'dde8ed9e92224dfeb83be77fcb64ebee.docx' },
  { slug: 'shift-leader', title: 'Shift Leader', industry: 'Restaurants & QSR', description: 'Floor leadership, cash handling, opening/closing, food safety oversight.', downloadUrl: DL + '793284fe50f2419790e359b69fd3e208.docx' },
  { slug: 'general-manager-restaurant', title: 'Restaurant General Manager', industry: 'Restaurants & QSR', description: 'P&L, food + labor cost management, hiring, brand standards.', downloadUrl: DL + '8785555143d74bd191088357fcb7ca12.docx' },
  { slug: 'delivery-driver', title: 'Delivery Driver', industry: 'Restaurants & QSR', description: 'Routing, customer service, vehicle maintenance, food-safe handling.', downloadUrl: DL + 'ea429071c6ed46efb12843bb0d045380.docx' },

  // Construction & Trades
  { slug: 'electrician', title: 'Electrician', industry: 'Construction & Trades', description: 'Wiring, code compliance (NEC), troubleshooting, blueprint reading.', downloadUrl: DL + '41d60c9db043420499c34976e42571e0.docx' },
  { slug: 'plumber', title: 'Plumber', industry: 'Construction & Trades', description: 'Installation, repair, code compliance, customer interaction.', downloadUrl: DL + '85150a85b32f4e70b32b2eed4005437c.docx' },
  { slug: 'hvac-technician', title: 'HVAC Technician', industry: 'Construction & Trades', description: 'Install, service, refrigerant handling (EPA 608), diagnostics.', downloadUrl: DL + 'e66609abdcc54d8ab3cbf679295382f0.docx' },
  { slug: 'carpenter', title: 'Carpenter', industry: 'Construction & Trades', description: 'Framing, finish work, blueprint reading, power tools, OSHA 10/30.', downloadUrl: DL + 'f22045f1bd394293b7299782cec0097a.docx' },
  { slug: 'project-superintendent', title: 'Project Superintendent', industry: 'Construction & Trades', description: 'Site supervision, subcontractor coordination, schedule, safety compliance.', downloadUrl: DL + '886da1815722446484263ecd9b44f944.docx' },
  { slug: 'safety-officer', title: 'Safety Officer', industry: 'Construction & Trades', description: 'OSHA compliance, JSAs, incident investigation, training.', downloadUrl: DL + '6fab2d52664545f39e7c6a546421ace2.docx' },

  // Manufacturing & Warehouse
  { slug: 'production-operator', title: 'Production Operator', industry: 'Manufacturing & Warehouse', description: 'Equipment operation, quality checks, lean basics, safety standards.', downloadUrl: DL + '1b0a0920406945c5be2a0df8c6881e1c.docx' },
  { slug: 'forklift-operator', title: 'Forklift Operator', industry: 'Manufacturing & Warehouse', description: 'OSHA-certified material handling, inventory accuracy, safety inspections.', downloadUrl: DL + 'd722e892c665459b9e58c53cae021568.docx' },
  { slug: 'warehouse-associate', title: 'Warehouse Associate', industry: 'Manufacturing & Warehouse', description: 'Picking + packing, RF scanning, receiving, putaway.', downloadUrl: DL + '653c06d629cf48b09d24d983c2370f04.docx' },
  { slug: 'shipping-receiving-clerk', title: 'Shipping & Receiving Clerk', industry: 'Manufacturing & Warehouse', description: 'BOL processing, carrier coordination, inventory transactions.', downloadUrl: DL + '1a45febc42f842849788fc2246a813b6.docx' },
  { slug: 'maintenance-technician', title: 'Maintenance Technician', industry: 'Manufacturing & Warehouse', description: 'Preventive + reactive maintenance, electrical + mechanical troubleshooting.', downloadUrl: DL + 'a22338aaf3684436b853b9a3ebc17db3.docx' },
  { slug: 'quality-inspector', title: 'Quality Inspector', industry: 'Manufacturing & Warehouse', description: 'Inspection, calipers + gauges, ISO documentation, NCR write-up.', downloadUrl: DL + '89b2be88b8634e30a428529a08180016.docx' },

  // Corporate & Professional
  { slug: 'hr-generalist', title: 'HR Generalist', industry: 'Corporate & Professional', description: 'Employee relations, benefits, onboarding, compliance, HRIS administration.', downloadUrl: DL + '029affb9b6524e9184aa166c664afd91.docx' },
  { slug: 'hr-business-partner', title: 'HR Business Partner', industry: 'Corporate & Professional', description: 'Strategic partnership with leadership, talent planning, change management.', downloadUrl: DL + '749651937f2b4b1a84c36dcbe3a69582.docx' },
  { slug: 'recruiter', title: 'Recruiter', industry: 'Corporate & Professional', description: 'Sourcing, screening, ATS management, hiring-manager partnership.', downloadUrl: DL + '8f8ab861715a4f98ac03b9485acad916.docx' },
  { slug: 'office-manager', title: 'Office Manager', industry: 'Corporate & Professional', description: 'Facilities, vendor management, AP support, executive admin.', downloadUrl: DL + '451492e6dd6b4949b4c7e781d00d510b.docx' },
  { slug: 'executive-assistant', title: 'Executive Assistant', industry: 'Corporate & Professional', description: 'Calendar + travel management, board prep, confidential project support.', downloadUrl: DL + 'b5e50d1630c346f3968cfc4faae81387.docx' },
  { slug: 'accountant', title: 'Accountant', industry: 'Corporate & Professional', description: 'GL maintenance, month-end close, reconciliations, audit support.', downloadUrl: DL + '37e88b644a3a4faa8ee014abba8b4104.docx' },
  { slug: 'bookkeeper', title: 'Bookkeeper', industry: 'Corporate & Professional', description: 'AP/AR, bank recs, payroll support, QuickBooks proficiency.', downloadUrl: DL + '5aaf31ed87fa4a298624cc18426e361f.docx' },
  { slug: 'payroll-specialist', title: 'Payroll Specialist', industry: 'Corporate & Professional', description: 'Multi-state payroll, tax filings, garnishments, compliance reporting.', downloadUrl: DL + '36c6e2faa9f84b5dafeb18724dcd8d64.docx' },
  { slug: 'paralegal', title: 'Paralegal', industry: 'Corporate & Professional', description: 'Legal research, document drafting, e-filing, case management.', downloadUrl: DL + '19969782b441457e8f5f1d8a09ad8526.docx' },

  // Tech & Engineering
  { slug: 'software-engineer', title: 'Software Engineer', industry: 'Tech & Engineering', description: 'Full-stack development, code review, on-call, modern web stack.', downloadUrl: DL + '4571c68be49849baab2275ca665803c0.docx' },
  { slug: 'senior-software-engineer', title: 'Senior Software Engineer', industry: 'Tech & Engineering', description: 'System design, mentorship, architecture decisions, cross-team partnership.', downloadUrl: DL + 'cbc20d42d1bf48098425cd7dc70b2751.docx' },
  { slug: 'product-manager', title: 'Product Manager', industry: 'Tech & Engineering', description: 'Roadmap, discovery, requirements, go-to-market partnership.', downloadUrl: DL + '63a71daf1ff74e2f931025914a44b1c0.docx' },
  { slug: 'designer', title: 'Product Designer', industry: 'Tech & Engineering', description: 'UX research, interaction design, design systems, prototyping.', downloadUrl: DL + 'aa07d7871e074b1ba6c31b2b88d577e0.docx' },
  { slug: 'devops-engineer', title: 'DevOps / SRE Engineer', industry: 'Tech & Engineering', description: 'Infrastructure-as-code, observability, on-call, deploy pipelines.', downloadUrl: DL + 'a9cd9465925347da9f5e2540bb5b1775.docx' },
  { slug: 'data-analyst', title: 'Data Analyst', industry: 'Tech & Engineering', description: 'SQL, dashboarding, A/B test analysis, stakeholder partnership.', downloadUrl: DL + '93f21062521d484eb155a42278ed1f77.docx' },
  { slug: 'it-support-specialist', title: 'IT Support Specialist', industry: 'Tech & Engineering', description: 'Tier-1/2 support, MDM, identity provisioning, SaaS administration.', downloadUrl: DL + 'a96dcee717fb41eaa2b7c3ea4910a60a.docx' },

  // Sales & Marketing
  { slug: 'account-executive', title: 'Account Executive', industry: 'Sales & Marketing', description: 'Full-cycle sales, quota carry, CRM hygiene, MEDDIC / SPICED qualification.', downloadUrl: DL + '49d1518b30de4b8c8c38a264b62552c7.docx' },
  { slug: 'sdr', title: 'Sales Development Representative', industry: 'Sales & Marketing', description: 'Outbound prospecting, sequence management, qualification, hand-off.', downloadUrl: DL + 'fe47d16efbc04293b6331224cc4de54a.docx' },
  { slug: 'customer-success-manager', title: 'Customer Success Manager', industry: 'Sales & Marketing', description: 'Onboarding, expansion, retention, QBRs, customer health.', downloadUrl: DL + 'e0e83642c0904468a9428cd9cd32ec1f.docx' },
  { slug: 'marketing-manager', title: 'Marketing Manager', industry: 'Sales & Marketing', description: 'Campaigns, channel management, content calendar, brand stewardship.', downloadUrl: DL + '929ff8cc1f1c4bac96074d0ca16c6880.docx' },
  { slug: 'content-marketer', title: 'Content Marketer', industry: 'Sales & Marketing', description: 'Blog, email, SEO, social, distribution + measurement.', downloadUrl: DL + '9fa94604f8004b1d86ae72f4722a324a.docx' },
  { slug: 'social-media-manager', title: 'Social Media Manager', industry: 'Sales & Marketing', description: 'Channel strategy, calendar, community management, paid social basics.', downloadUrl: DL + 'c588091d09ed4e08b3fadf8d56976f60.docx' },
]
