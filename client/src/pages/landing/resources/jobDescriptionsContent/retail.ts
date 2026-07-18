import type { JDContent } from './types'

export const retail: Record<string, JDContent> = {
  'retail-sales-associate': {
    summary: 'The Retail Sales Associate delivers an exceptional customer experience on the sales floor by greeting shoppers, providing product knowledge, and closing sales. You will maintain merchandising standards, process transactions accurately, and support loss prevention through awareness and adherence to policy.',
    responsibilities: [
      'Welcome customers, identify needs, and recommend products using consultative selling techniques',
      'Operate the POS system to process cash, credit, and digital payment transactions',
      'Execute merchandising standards including sizing, folding, and replenishment',
      'Assist with inventory counts, receiving shipments, and organizing stockroom',
      'Handle returns, exchanges, and customer complaints professionally',
      'Maintain awareness of shoplifting indicators and report concerns to management',
      'Meet individual and team sales goals as set by store leadership',
    ],
    requirements: [
      'High school diploma or equivalent',
      '1+ year of retail or customer-service experience',
      'Strong communication and interpersonal skills',
      'Ability to stand for extended periods and lift up to 30 lbs',
      'Availability to work evenings, weekends, and peak retail seasons',
    ],
    preferred: [
      "Product knowledge in the store's merchandise category",
      'Experience with a specific POS platform (Square, Lightspeed, Shopify POS)',
      'Proven track record of meeting sales metrics',
    ],
  },

  'cashier': {
    summary: 'The Cashier processes customer transactions quickly and accurately while providing friendly service. You will handle cash and electronic payments, assist with returns, and ensure the checkout area is organized and stocked.',
    responsibilities: [
      'Scan and ring up customer purchases accurately using the POS system',
      'Process cash, credit/debit card, check, and digital payment methods',
      'Issue receipts, refunds, change, and vouchers per company policy',
      'Verify customer identification for age-restricted products as required',
      'Bag or package merchandise carefully to prevent damage',
      'Maintain a clean, organized checkout lane and restock impulse-buy areas',
      'Balance cash drawer at the start and end of each shift',
    ],
    requirements: [
      'High school diploma or equivalent',
      'Basic math skills and comfort handling cash',
      'Reliable, punctual, and customer-focused work ethic',
      'Ability to stand for an entire shift',
      'Availability to work varied shifts including weekends and holidays',
    ],
    preferred: [
      'Prior cashier or retail experience',
      'Experience with specific POS systems',
      'Bilingual communication skills',
    ],
  },

  'store-manager': {
    summary: "The Store Manager owns the full performance of a retail location — from people management and scheduling to P&L oversight and brand execution. You will hire, develop, and retain a high-performing team, drive sales results, and ensure the store operates in compliance with all company and regulatory standards.",
    responsibilities: [
      'Oversee all daily store operations including opening/closing procedures and cash management',
      'Recruit, interview, hire, onboard, and train store associates and supervisors',
      'Build and manage team schedules to align labor hours with sales volume and budget',
      'Analyze P&L reports, monitor shrink, and implement action plans to hit financial targets',
      'Drive sales and conversion through coaching, floor presence, and customer engagement',
      'Enforce visual merchandising and product placement standards from corporate',
      'Handle escalated customer concerns and ensure consistent service standards',
      'Conduct performance reviews, coaching sessions, and disciplinary actions as needed',
    ],
    requirements: [
      '3+ years of retail management experience, including full P&L ownership',
      'Demonstrated success in team development and performance management',
      'Strong analytical skills and comfort with sales reporting tools',
      'Excellent communication and leadership skills',
      'Flexibility to work varied shifts including evenings, weekends, and holidays',
    ],
    preferred: [
      'Experience managing a multi-million-dollar volume location',
      "Bachelor's degree in Business, Retail Management, or related field",
      'Familiarity with workforce management software (Kronos, Workday)',
    ],
  },

  'assistant-store-manager': {
    summary: "The Assistant Store Manager supports the Store Manager in all operational and people functions. You will lead shifts, open and close the store, train team members, and serve as acting store manager in the SM's absence.",
    responsibilities: [
      'Lead the sales floor and manage team performance during assigned shifts',
      'Execute opening and closing procedures including cash reconciliation and security checks',
      'Assist in recruiting, onboarding, and training new associates',
      'Monitor and communicate daily, weekly, and monthly sales KPIs to the team',
      'Resolve customer issues and complaints in a fair and brand-consistent manner',
      'Execute floor sets, promotional changes, and visual merchandising directives',
      'Support inventory management including cycle counts and shrink prevention',
    ],
    requirements: [
      '2+ years of retail experience including at least 1 year in a supervisory role',
      'Strong coaching and team-motivation skills',
      'Proven ability to meet and exceed sales and service metrics',
      'Availability to work varied shifts, weekends, and holidays',
      'Basic proficiency with retail reporting and scheduling tools',
    ],
    preferred: [
      'Experience with P&L review and labor management',
      'Readiness for promotion to Store Manager within 12 months',
      'Brand-specific product knowledge',
    ],
  },

  'visual-merchandiser': {
    summary: 'The Visual Merchandiser brings the brand to life by creating compelling window and floor displays that drive traffic and conversion. You will execute planograms, develop creative installations, and ensure all visual standards are maintained across the store.',
    responsibilities: [
      'Design and install window displays, mannequin styling, and floor fixtures to brand standards',
      'Interpret and execute planograms and visual directives from corporate',
      'Partner with the Store Manager on product placement strategies to maximize sell-through',
      'Adapt seasonal and promotional displays on schedule',
      'Conduct regular store walks to identify and correct visual inconsistencies',
      'Train store associates on basic folding, sizing, and display maintenance',
      'Photograph finished displays for corporate reporting',
    ],
    requirements: [
      '2+ years of visual merchandising or display experience in retail',
      'Strong aesthetic sensibility and creative problem-solving skills',
      'Ability to interpret and execute corporate visual direction',
      'Physical ability to lift fixtures, climb ladders, and work in stockroom environments',
      'Portfolio of past display work preferred',
    ],
    preferred: [
      'Degree or certificate in Fashion Merchandising, Visual Communications, or related field',
      'Experience with Adobe Creative Suite for creating display schematics',
      'Multi-location or field visual merchandising experience',
    ],
  },

  'stock-associate': {
    summary: 'The Stock Associate ensures the sales floor and stockroom are organized, fully replenished, and accurately inventoried. You will receive and process shipments, restock merchandise, and support the store team in maintaining a neat, shoppable environment.',
    responsibilities: [
      'Receive, open, and process incoming merchandise shipments accurately',
      'Replenish sales floor product based on sell-through and visual standards',
      'Organize and maintain a logical, efficient stockroom layout',
      'Conduct cycle counts and assist with full physical inventory events',
      'Return go-backs and pulls to their correct stockroom locations',
      'Prepare outbound transfers and damage claims per company procedure',
      'Support floor associates during peak traffic periods',
    ],
    requirements: [
      'High school diploma or equivalent',
      'Ability to lift up to 50 lbs and stand for extended periods',
      'Organized and detail-oriented work style',
      'Availability to work early-morning stocking shifts, weekends, and holidays',
      'Basic math skills for inventory tracking',
    ],
    preferred: [
      'Prior retail stock or warehouse associate experience',
      'Familiarity with inventory management software',
      'Forklift or pallet jack certification',
    ],
  },
}
