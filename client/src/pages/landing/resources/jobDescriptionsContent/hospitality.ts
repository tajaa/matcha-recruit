import type { JDContent } from './types'

export const hospitality: Record<string, JDContent> = {
  'front-desk-agent': {
    summary: 'The Front Desk Agent is the first point of contact for guests and plays a central role in shaping the guest experience. You will manage arrivals and departures, handle reservations, respond to inquiries, and coordinate with housekeeping and other departments to ensure every stay exceeds expectations.',
    responsibilities: [
      'Check guests in and out efficiently using the property management system (PMS)',
      'Process payments, post charges, and reconcile cash drawer at shift end',
      'Respond to phone, email, and in-person inquiries with professionalism',
      'Coordinate room assignments and communicate special requests to housekeeping',
      'Handle guest complaints, escalating to management when appropriate',
      'Provide concierge-level recommendations for dining, transportation, and local attractions',
      'Maintain accurate guest records and uphold data privacy standards',
    ],
    requirements: [
      'High school diploma or equivalent; hospitality certificate a plus',
      '1+ year of front-desk, customer service, or hospitality experience',
      'Proficiency with a PMS (Opera, Cloudbeds, or similar)',
      'Strong verbal and written communication skills',
      'Ability to stand for extended periods and work varied shifts including nights and weekends',
    ],
    preferred: [
      'Experience in a hotel branded under a major flag (Marriott, Hilton, IHG, etc.)',
      'Bilingual or multilingual communication skills',
      'Familiarity with loyalty program administration',
    ],
  },

  'housekeeper': {
    summary: 'The Housekeeper maintains the cleanliness and presentation of guest rooms and public areas to brand standards. You will be responsible for efficient room turnover, proper handling of linens and amenities, and adherence to health and safety protocols.',
    responsibilities: [
      'Clean and prepare guest rooms including making beds, vacuuming, dusting, and sanitizing bathrooms',
      'Replenish guest amenities, towels, and linens to established par levels',
      'Report maintenance issues, missing items, or suspicious activity to supervisors',
      'Follow lost-and-found procedures accurately and promptly',
      'Maintain housekeeping cart in an organized and stocked condition',
      'Complete room assignments within allotted time to meet occupancy goals',
    ],
    requirements: [
      'Ability to perform physically demanding tasks including lifting up to 30 lbs and prolonged standing',
      'Attention to detail and commitment to cleanliness standards',
      'Ability to work independently with minimal supervision',
      'Availability to work weekends, holidays, and early-morning shifts',
    ],
    preferred: [
      'Prior housekeeping experience in a hotel or resort environment',
      'Familiarity with chemical handling and OSHA safety standards',
      'Basic English communication skills for team coordination',
    ],
  },

  'housekeeping-supervisor': {
    summary: 'The Housekeeping Supervisor oversees a team of housekeepers to ensure rooms and public areas are cleaned and maintained to brand and regulatory standards. You will schedule staff, conduct quality audits, manage supply inventory, and serve as a hands-on resource for your team.',
    responsibilities: [
      'Plan and assign daily room assignments and public-area tasks to housekeeping staff',
      'Conduct room and area inspections to verify compliance with brand cleanliness standards',
      'Train new housekeepers on procedures, chemical use, and safety protocols',
      'Maintain par levels for linens, amenities, and cleaning supplies; submit procurement requests',
      'Document and follow up on maintenance requests and guest property incidents',
      'Manage lost-and-found log and escalate unresolved items to management',
      'Prepare shift reports and track key housekeeping KPIs (room score, turnaround time)',
    ],
    requirements: [
      '2+ years of housekeeping experience, including at least 6 months in a lead or supervisory role',
      'Strong organizational and time-management skills',
      'Ability to lift up to 30 lbs and perform physical tasks as needed',
      'Availability to work varied shifts including early mornings, weekends, and holidays',
      'Basic computer skills for scheduling and reporting',
    ],
    preferred: [
      'Experience with hotel PMS or housekeeping management apps (HotSOS, Knowcross)',
      'OSHA 10 certification',
      'Bilingual skills to support a diverse housekeeping team',
    ],
  },

  'concierge': {
    summary: 'The Concierge serves as a personal advisor to hotel guests, anticipating needs and curating exceptional local experiences. From arranging transportation to securing hard-to-get restaurant reservations, you will deliver white-glove service that drives loyalty and repeat stays.',
    responsibilities: [
      'Greet guests warmly and proactively identify opportunities to enhance their stay',
      'Arrange reservations for dining, entertainment, spa, transportation, and tours',
      'Provide personalized recommendations and insider knowledge of the local area',
      'Coordinate VIP arrivals, amenity deliveries, and special-occasion arrangements',
      'Manage luggage storage, mail handling, and package acceptance',
      'Maintain relationships with local vendors, restaurants, and cultural venues',
      'Document guest preferences for future visits and share with relevant departments',
    ],
    requirements: [
      '2+ years of concierge, guest services, or luxury hospitality experience',
      'Exceptional interpersonal and communication skills',
      'Deep knowledge of local dining, entertainment, and cultural offerings',
      'Proficiency with reservation platforms and PMS software',
      'Professional appearance and demeanor',
    ],
    preferred: [
      "Les Clefs d'Or membership or active pursuit of concierge certification",
      'Multilingual communication abilities',
      'Experience in a Forbes 4- or 5-star property',
    ],
  },

  'event-coordinator': {
    summary: 'The Event Coordinator manages the planning and on-site execution of social, corporate, and catering events. You will own the banquet event order (BEO) process from initial inquiry through post-event follow-up, coordinating vendors, AV, catering, and setup crews to deliver flawless events.',
    responsibilities: [
      'Respond to event inquiries, conduct site tours, and prepare proposals and contracts',
      'Develop and manage banquet event orders (BEOs) as the single source of event truth',
      'Coordinate with catering, AV, décor, and external vendors to execute event logistics',
      'Conduct pre-event walkthroughs and ensure all setups meet client specifications',
      'Serve as on-site point of contact during events, managing timelines and resolving issues',
      'Reconcile event invoices and process post-event billing accurately',
      'Gather post-event feedback and maintain client relationships for repeat business',
    ],
    requirements: [
      '2+ years of event planning or catering-sales experience in a hotel or venue',
      'Strong project-management and multitasking abilities',
      'Experience with event-management or catering software (Delphi, Tripleseat, or similar)',
      'Excellent written and verbal communication for client-facing interactions',
      'Ability to work evenings, weekends, and holidays as events demand',
    ],
    preferred: [
      'CMP (Certified Meeting Professional) or similar designation',
      'Experience managing events for 200+ attendees',
      'Familiarity with AV production and hybrid event technology',
    ],
  },
}
