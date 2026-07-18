import type { JDContent } from './types'

export const trades: Record<string, JDContent> = {
  'electrician': {
    summary: 'The Electrician installs, maintains, and repairs electrical systems in residential, commercial, or industrial settings. You will read blueprints and wiring diagrams, ensure compliance with the NEC and local codes, troubleshoot faults, and perform work safely at all times.',
    responsibilities: [
      'Install, maintain, and repair electrical wiring, fixtures, equipment, and controls',
      'Read and interpret blueprints, schematics, and electrical diagrams',
      'Test and troubleshoot electrical systems using meters, oscilloscopes, and diagnostic tools',
      'Ensure all work complies with the National Electrical Code (NEC) and applicable local codes',
      'Collaborate with general contractors, project managers, and inspectors on project requirements',
      'Complete material take-offs and assist with project scheduling',
      'Maintain a safe jobsite and adhere to OSHA electrical safety standards',
    ],
    requirements: [
      'Journeyman Electrician license in applicable state (or Apprentice with equivalent experience)',
      '3+ years of commercial or industrial electrical experience',
      'Proficiency with NEC code compliance and permit processes',
      'OSHA 10 certification (OSHA 30 preferred)',
      'Ability to lift up to 50 lbs and work in confined spaces, at heights, and in varied weather',
    ],
    preferred: [
      'Master Electrician license',
      'Experience with industrial motor controls, PLC systems, or solar/battery installations',
      'First Aid/CPR certification',
    ],
  },

  'plumber': {
    summary: 'The Plumber installs, services, and repairs plumbing systems in new construction and existing residential or commercial structures. You will interpret blueprints, diagnose system issues, ensure code compliance, and deliver reliable craftsmanship on every job.',
    responsibilities: [
      'Install, repair, and maintain pipes, fixtures, water heaters, and drainage systems',
      'Read and interpret blueprints, isometric drawings, and plumbing layouts',
      'Diagnose system failures using pressure tests, leak detection, and camera inspection tools',
      'Ensure all work complies with local plumbing codes and obtain permits as required',
      'Coordinate with general contractors and inspection authorities on project timelines',
      'Manage material requirements and maintain a clean, organized work vehicle',
      'Respond to service calls and emergency repairs as dispatched',
    ],
    requirements: [
      'Journeyman Plumber license in applicable state',
      '3+ years of plumbing experience in residential, commercial, or service settings',
      'Knowledge of local plumbing codes and permit processes',
      'OSHA 10 certification',
      "Valid driver's license",
    ],
    preferred: [
      'Master Plumber license',
      'Experience with hydronic heating, medical gas, or backflow prevention systems',
      'EPA 608 Universal certification',
    ],
  },

  'hvac-technician': {
    summary: 'The HVAC Technician installs, services, and repairs heating, ventilation, air conditioning, and refrigeration systems. You will handle refrigerant management, diagnose mechanical and electrical faults, ensure code compliance, and deliver outstanding technical service to commercial and/or residential clients.',
    responsibilities: [
      'Install, start up, and commission HVAC/R equipment per manufacturer and code specifications',
      'Perform preventive maintenance on heating, cooling, and ventilation systems',
      'Diagnose and repair mechanical, electrical, and control-system failures',
      'Handle refrigerants in accordance with EPA Section 608 regulations',
      'Review service history and document all work completed in the service management system',
      'Educate clients on equipment operation, maintenance, and efficiency improvements',
      'Maintain company vehicle and stock of commonly used parts and tools',
    ],
    requirements: [
      'EPA 608 Universal certification (Type I/II/III)',
      '3+ years of HVAC/R installation or service experience',
      'Proficiency with electrical troubleshooting tools and HVAC diagnostic equipment',
      "Valid driver's license with a clean record",
      'Ability to work in confined spaces, at heights, and in extreme temperatures',
    ],
    preferred: [
      'NATE (North American Technician Excellence) certification',
      'Experience with Building Automation Systems (BAS/BMS)',
      'OSHA 10 or 30 certification',
    ],
  },

  'carpenter': {
    summary: 'The Carpenter performs framing, finish carpentry, and cabinetry work on residential and commercial construction projects. You will read blueprints, select appropriate materials, use hand and power tools safely, and deliver high-quality craftsmanship on schedule.',
    responsibilities: [
      'Perform rough framing, sheathing, and structural wood assembly per blueprints',
      'Install doors, windows, trim, cabinets, and finish carpentry elements',
      'Read and interpret construction drawings and cut sheets',
      'Select, measure, cut, and shape materials with precision',
      'Collaborate with subcontractors and trades to coordinate installation sequences',
      'Maintain a clean, organized, and safe work area at all times',
      'Complete work in compliance with local building codes and OSHA safety standards',
    ],
    requirements: [
      '3+ years of carpentry experience in residential or commercial construction',
      'Proficiency with power tools, nail guns, and basic measuring equipment',
      'Blueprint reading skills',
      'OSHA 10 certification',
      'Ability to lift up to 50 lbs and work at heights using ladders and scaffolding',
    ],
    preferred: [
      'Journeyman Carpenter union card or equivalent certification',
      'Finish carpentry or millwork specialization',
      'First Aid/CPR certification',
    ],
  },

  'project-superintendent': {
    summary: 'The Project Superintendent is the on-site authority for construction project delivery. You will coordinate all trades, maintain the project schedule, enforce safety compliance, and serve as the primary point of contact for owners, architects, and inspectors — ensuring the project finishes on time, on budget, and defect-free.',
    responsibilities: [
      'Direct day-to-day field operations and coordinate subcontractor and material schedules',
      'Maintain and update the master construction schedule; identify and resolve sequencing conflicts',
      'Conduct daily site walks to monitor quality, safety, and progress against milestones',
      'Serve as the primary site contact for owners, architects, engineers, and inspectors',
      'Run weekly owner-architect-contractor (OAC) and subcontractor coordination meetings',
      'Review and approve subcontractor work for quality and code compliance before concealment',
      'Investigate and document all incidents, near-misses, and non-conformances',
    ],
    requirements: [
      '7+ years of commercial construction field experience, including 3+ years as superintendent',
      'Strong knowledge of all trades, construction sequences, and building codes',
      'Proficiency with construction management software (Procore, Bluebeam, MS Project)',
      'OSHA 30 certification',
      "Valid driver's license",
    ],
    preferred: [
      'LEED AP or equivalent sustainability credential',
      'Experience on projects valued at $10M or more',
      'First Aid/AED/CPR certification',
    ],
  },

  'safety-officer': {
    summary: 'The Safety Officer develops, implements, and enforces workplace health and safety programs to protect employees, subcontractors, and the public. You will conduct inspections, lead incident investigations, deliver training, and ensure full compliance with OSHA regulations and company safety policy.',
    responsibilities: [
      'Develop and update the site-specific Health and Safety Plan (HASP) and Job Safety Analyses (JSAs)',
      'Conduct regular site inspections and audits to identify and correct hazardous conditions',
      'Lead incident, near-miss, and first-aid investigations; complete required reporting',
      'Deliver OSHA-compliant safety orientations, toolbox talks, and specialized training',
      'Maintain all required safety records including training logs, inspection reports, and OSHA 300 logs',
      'Liaise with OSHA, insurance carriers, and clients on safety compliance matters',
      'Recommend and monitor corrective action plans to close identified gaps',
    ],
    requirements: [
      "Bachelor's degree in Occupational Safety, Industrial Hygiene, or related field (or equivalent experience)",
      'OSHA 30 construction or general industry certification',
      '3+ years of EHS or safety-officer experience in construction, manufacturing, or industrial settings',
      'Strong knowledge of OSHA 1910 and 1926 standards',
      'Excellent communication and training facilitation skills',
    ],
    preferred: [
      'Certified Safety Professional (CSP) or Associate Safety Professional (ASP) designation',
      'Experience with ISO 45001 or OHSAS 18001 management systems',
      'First Aid/CPR instructor certification',
    ],
  },
}
