import type { JDContent } from './types'

export const technology: Record<string, JDContent> = {
  'software-engineer': {
    summary: 'The Software Engineer designs, builds, and ships features on a modern web or mobile stack. You will write clean, tested code, participate in code reviews, collaborate with product and design, and share in on-call responsibilities — taking real ownership of the systems you build.',
    responsibilities: [
      'Design and implement features across the full stack (frontend and/or backend depending on team)',
      'Write comprehensive unit, integration, and end-to-end tests',
      'Participate in code reviews and hold yourself and teammates to high engineering standards',
      'Collaborate with Product and Design to define requirements and shape technical approach',
      'Monitor production systems, respond to incidents, and perform root cause analysis',
      'Document architecture decisions and maintain up-to-date technical documentation',
      'Contribute to engineering-wide initiatives including tooling, reliability, and developer experience',
    ],
    requirements: [
      "Bachelor's degree in Computer Science, Engineering, or equivalent practical experience",
      '2+ years of professional software development experience',
      'Proficiency in at least one modern programming language (Python, TypeScript/JavaScript, Go, Java, etc.)',
      'Familiarity with cloud platforms (AWS, GCP, or Azure) and containerization (Docker, Kubernetes)',
      'Strong problem-solving skills and intellectual curiosity',
    ],
    preferred: [
      'Experience with the specific stack used by the team',
      'Open-source contributions or side projects demonstrating technical depth',
      'Familiarity with distributed systems, event-driven architecture, or data engineering',
    ],
  },

  'senior-software-engineer': {
    summary: 'The Senior Software Engineer drives technical excellence on the team — setting the design bar, mentoring engineers, and leading delivery of complex, high-impact systems. You will be equally comfortable writing production code and influencing the technical roadmap, and you will help define what great looks like for the engineering org.',
    responsibilities: [
      'Lead the design and implementation of complex, cross-functional features and platform improvements',
      'Produce technical design documents and drive architectural decision records (ADRs)',
      'Mentor junior and mid-level engineers through code reviews, pairing, and design critiques',
      'Partner with Product and Engineering leadership to scope and estimate roadmap initiatives',
      'Establish and uphold engineering standards for quality, reliability, and security',
      'Investigate and resolve complex production incidents and systemic reliability issues',
      'Represent engineering perspective in cross-functional planning and prioritization',
    ],
    requirements: [
      '5+ years of software engineering experience with a track record of shipping impactful systems',
      'Deep proficiency in at least one language and demonstrated polyglot capability',
      'Experience designing and operating distributed systems at scale',
      'Strong mentorship and technical communication skills',
      'Demonstrated ownership of production systems through the full lifecycle',
    ],
    preferred: [
      'Staff or tech-lead experience with cross-team influence',
      'Domain expertise relevant to the team (e.g., payments, identity, data pipelines)',
      'Published engineering blog posts or conference talks',
    ],
  },

  'product-manager': {
    summary: 'The Product Manager owns the product roadmap for one or more product areas. You will discover problems worth solving, define requirements in close partnership with engineering and design, and drive go-to-market execution — ensuring the team ships products that delight users and move business metrics.',
    responsibilities: [
      'Develop and maintain a prioritized product roadmap grounded in user research and business strategy',
      'Write detailed product requirements documents (PRDs) and user stories with clear acceptance criteria',
      'Conduct user interviews, usability studies, and competitive analysis to continuously improve product intuition',
      'Partner with Engineering and Design in sprint planning, grooming, and retrospectives',
      'Define and track success metrics; analyze usage data to make informed product decisions',
      'Drive go-to-market planning in partnership with Marketing, Sales, and Customer Success',
      'Communicate roadmap and progress to stakeholders and leadership',
    ],
    requirements: [
      '3+ years of product management experience in a B2B or B2C software environment',
      'Proven ability to translate ambiguous problems into clear product requirements',
      'Strong analytical skills and comfort with product analytics tools (Amplitude, Mixpanel, Looker)',
      'Excellent written and verbal communication skills',
      'Demonstrated experience shipping product from zero to one',
    ],
    preferred: [
      'MBA or relevant advanced degree',
      'Technical background or experience working on API/platform products',
      'Experience with growth or monetization product areas',
    ],
  },

  'designer': {
    summary: 'The Product Designer shapes the end-to-end experience of our product — from user research and concept validation through pixel-perfect UI. You will own design across one or more product surfaces, contribute to the design system, and collaborate closely with Product and Engineering to ship work that is both beautiful and functional.',
    responsibilities: [
      'Lead UX research including user interviews, usability testing, and synthesis',
      'Create wireframes, interaction flows, prototypes, and high-fidelity UI designs',
      'Contribute to and maintain the design system, ensuring consistency across the product',
      'Collaborate with Product Managers to define problems and evaluate solutions',
      'Work closely with engineers during implementation to preserve design intent',
      'Conduct design critiques and mentor junior designers on craft and process',
      'Stay current with accessibility standards (WCAG 2.1) and apply them throughout',
    ],
    requirements: [
      '3+ years of product design experience at a software company',
      'Expert proficiency with Figma and design system tooling',
      'Strong portfolio demonstrating end-to-end product thinking and visual craft',
      'Experience conducting and synthesizing UX research',
      'Ability to communicate design rationale to cross-functional stakeholders',
    ],
    preferred: [
      'Experience designing complex data-heavy or enterprise products',
      'Familiarity with front-end development (CSS, React basics) for better engineering partnership',
      'Motion design skills',
    ],
  },

  'devops-engineer': {
    summary: 'The DevOps / Site Reliability Engineer builds and maintains the infrastructure, tooling, and processes that keep production reliable and enable engineering teams to ship fast and confidently. You will own CI/CD pipelines, cloud infrastructure, observability, and incident response for critical systems.',
    responsibilities: [
      'Design, build, and maintain cloud infrastructure using infrastructure-as-code (Terraform, Pulumi, CDK)',
      'Own and improve CI/CD pipelines for fast, safe, and automated deployments',
      'Build and maintain observability stack including logging, metrics, alerting, and distributed tracing',
      'Participate in on-call rotation and lead incident response and post-mortems',
      'Harden production environments for security, compliance, and reliability',
      'Collaborate with engineering teams to establish SLOs and drive reliability improvements',
      'Evaluate and adopt new tools and practices that improve developer experience and system performance',
    ],
    requirements: [
      '3+ years of DevOps, Platform Engineering, or SRE experience',
      'Proficiency with cloud platforms (AWS, GCP, or Azure) and containerization (Kubernetes, Docker)',
      'Experience with infrastructure-as-code tools and GitOps practices',
      'Strong scripting ability in Python, Bash, or Go',
      'Deep understanding of networking, security, and distributed systems fundamentals',
    ],
    preferred: [
      'AWS/GCP/Azure Professional-level certification',
      'Experience with service mesh (Istio, Linkerd) or eBPF-based observability',
      'Background in a high-traffic, SLA-critical production environment',
    ],
  },

  'data-analyst': {
    summary: 'The Data Analyst transforms raw data into actionable insights that guide product, marketing, and business decisions. You will own analytical projects end to end — from data extraction and modeling through dashboarding and stakeholder communication — and act as a trusted data resource for your assigned business areas.',
    responsibilities: [
      'Write efficient SQL queries to extract, transform, and analyze data from the data warehouse',
      'Build and maintain self-service dashboards and reports in BI tools (Looker, Tableau, Metabase)',
      'Design and analyze A/B tests including experimental design, sample sizing, and results interpretation',
      'Proactively identify trends, anomalies, and opportunities through exploratory data analysis',
      'Partner with Product, Marketing, and Operations stakeholders to frame business questions and deliver insights',
      'Document data models, metric definitions, and analytical methodologies',
      'Contribute to data quality monitoring and pipeline reliability',
    ],
    requirements: [
      '2+ years of data analyst or business intelligence experience',
      'Advanced SQL proficiency across multiple dialects (PostgreSQL, BigQuery, Snowflake, or similar)',
      'Experience with at least one BI tool (Looker, Tableau, Power BI, Metabase)',
      'Strong analytical reasoning and ability to communicate findings to non-technical audiences',
      'Solid understanding of statistical concepts relevant to A/B testing',
    ],
    preferred: [
      'Proficiency in Python or R for advanced analysis',
      'dbt experience for data modeling and transformation',
      'Background in product analytics, growth, or marketing analytics',
    ],
  },

  'it-support-specialist': {
    summary: 'The IT Support Specialist provides Tier 1 and Tier 2 technical support to employees, ensuring fast, effective resolution of hardware, software, and connectivity issues. You will manage device provisioning, SaaS access, identity lifecycle, and endpoint management to keep the organization running securely and productively.',
    responsibilities: [
      'Serve as first point of contact for IT support requests via ticketing system, chat, and walk-up',
      'Diagnose and resolve hardware, software, network, and peripheral issues for Mac, Windows, and mobile devices',
      'Provision and deploy laptops, phones, and other endpoints using MDM (Jamf, Intune, or similar)',
      'Manage user accounts, groups, and permissions across identity platforms (Okta, Azure AD, Google Workspace)',
      'Onboard new employees by provisioning equipment, access, and conducting IT orientation',
      'Maintain IT asset inventory, hardware lifecycle tracking, and license management',
      'Escalate complex issues to Tier 3 or managed service provider and track to resolution',
    ],
    requirements: [
      '2+ years of IT support or helpdesk experience',
      'Proficiency supporting macOS and Windows environments',
      'Experience with MDM platforms (Jamf, Intune, or equivalent) and SSO/identity tools (Okta, Azure AD)',
      'Strong troubleshooting methodology and documentation habits',
      'Customer-service mindset with clear, patient communication skills',
    ],
    preferred: [
      'CompTIA A+, Network+, or Security+ certification',
      'Experience in a SaaS-heavy, cloud-first company environment',
      'Basic scripting ability (Bash, PowerShell) for automation',
    ],
  },
}
