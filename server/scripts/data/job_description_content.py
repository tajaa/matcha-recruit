"""Hardcoded content for all 62 job description templates.

Each entry: slug -> {summary, responsibilities, requirements, preferred}
"""

EEO_STATEMENT = (
    "We are an equal opportunity employer. All qualified applicants will receive "
    "consideration for employment without regard to race, color, religion, sex, "
    "sexual orientation, gender identity, national origin, disability, veteran status, "
    "or any other characteristic protected by applicable law."
)

JD_CONTENT: dict[str, dict] = {

    # ── Hospitality ────────────────────────────────────────────────────────────

    "front-desk-agent": {
        "summary": (
            "The Front Desk Agent is the first point of contact for guests and plays a "
            "central role in shaping the guest experience. You will manage arrivals and "
            "departures, handle reservations, respond to inquiries, and coordinate with "
            "housekeeping and other departments to ensure every stay exceeds expectations."
        ),
        "responsibilities": [
            "Check guests in and out efficiently using the property management system (PMS)",
            "Process payments, post charges, and reconcile cash drawer at shift end",
            "Respond to phone, email, and in-person inquiries with professionalism",
            "Coordinate room assignments and communicate special requests to housekeeping",
            "Handle guest complaints, escalating to management when appropriate",
            "Provide concierge-level recommendations for dining, transportation, and local attractions",
            "Maintain accurate guest records and uphold data privacy standards",
        ],
        "requirements": [
            "High school diploma or equivalent; hospitality certificate a plus",
            "1+ year of front-desk, customer service, or hospitality experience",
            "Proficiency with a PMS (Opera, Cloudbeds, or similar)",
            "Strong verbal and written communication skills",
            "Ability to stand for extended periods and work varied shifts including nights and weekends",
        ],
        "preferred": [
            "Experience in a hotel branded under a major flag (Marriott, Hilton, IHG, etc.)",
            "Bilingual or multilingual communication skills",
            "Familiarity with loyalty program administration",
        ],
    },

    "housekeeper": {
        "summary": (
            "The Housekeeper maintains the cleanliness and presentation of guest rooms and "
            "public areas to brand standards. You will be responsible for efficient room "
            "turnover, proper handling of linens and amenities, and adherence to health and "
            "safety protocols."
        ),
        "responsibilities": [
            "Clean and prepare guest rooms including making beds, vacuuming, dusting, and sanitizing bathrooms",
            "Replenish guest amenities, towels, and linens to established par levels",
            "Report maintenance issues, missing items, or suspicious activity to supervisors",
            "Follow lost-and-found procedures accurately and promptly",
            "Maintain housekeeping cart in an organized and stocked condition",
            "Complete room assignments within allotted time to meet occupancy goals",
        ],
        "requirements": [
            "Ability to perform physically demanding tasks including lifting up to 30 lbs and prolonged standing",
            "Attention to detail and commitment to cleanliness standards",
            "Ability to work independently with minimal supervision",
            "Availability to work weekends, holidays, and early-morning shifts",
        ],
        "preferred": [
            "Prior housekeeping experience in a hotel or resort environment",
            "Familiarity with chemical handling and OSHA safety standards",
            "Basic English communication skills for team coordination",
        ],
    },

    "housekeeping-supervisor": {
        "summary": (
            "The Housekeeping Supervisor oversees a team of housekeepers to ensure rooms and "
            "public areas are cleaned and maintained to brand and regulatory standards. You will "
            "schedule staff, conduct quality audits, manage supply inventory, and serve as a "
            "hands-on resource for your team."
        ),
        "responsibilities": [
            "Plan and assign daily room assignments and public-area tasks to housekeeping staff",
            "Conduct room and area inspections to verify compliance with brand cleanliness standards",
            "Train new housekeepers on procedures, chemical use, and safety protocols",
            "Maintain par levels for linens, amenities, and cleaning supplies; submit procurement requests",
            "Document and follow up on maintenance requests and guest property incidents",
            "Manage lost-and-found log and escalate unresolved items to management",
            "Prepare shift reports and track key housekeeping KPIs (room score, turnaround time)",
        ],
        "requirements": [
            "2+ years of housekeeping experience, including at least 6 months in a lead or supervisory role",
            "Strong organizational and time-management skills",
            "Ability to lift up to 30 lbs and perform physical tasks as needed",
            "Availability to work varied shifts including early mornings, weekends, and holidays",
            "Basic computer skills for scheduling and reporting",
        ],
        "preferred": [
            "Experience with hotel PMS or housekeeping management apps (HotSOS, Knowcross)",
            "OSHA 10 certification",
            "Bilingual skills to support a diverse housekeeping team",
        ],
    },

    "concierge": {
        "summary": (
            "The Concierge serves as a personal advisor to hotel guests, anticipating needs and "
            "curating exceptional local experiences. From arranging transportation to securing "
            "hard-to-get restaurant reservations, you will deliver white-glove service that drives "
            "loyalty and repeat stays."
        ),
        "responsibilities": [
            "Greet guests warmly and proactively identify opportunities to enhance their stay",
            "Arrange reservations for dining, entertainment, spa, transportation, and tours",
            "Provide personalized recommendations and insider knowledge of the local area",
            "Coordinate VIP arrivals, amenity deliveries, and special-occasion arrangements",
            "Manage luggage storage, mail handling, and package acceptance",
            "Maintain relationships with local vendors, restaurants, and cultural venues",
            "Document guest preferences for future visits and share with relevant departments",
        ],
        "requirements": [
            "2+ years of concierge, guest services, or luxury hospitality experience",
            "Exceptional interpersonal and communication skills",
            "Deep knowledge of local dining, entertainment, and cultural offerings",
            "Proficiency with reservation platforms and PMS software",
            "Professional appearance and demeanor",
        ],
        "preferred": [
            "Les Clefs d'Or membership or active pursuit of concierge certification",
            "Multilingual communication abilities",
            "Experience in a Forbes 4- or 5-star property",
        ],
    },

    "event-coordinator": {
        "summary": (
            "The Event Coordinator manages the planning and on-site execution of social, corporate, "
            "and catering events. You will own the banquet event order (BEO) process from initial "
            "inquiry through post-event follow-up, coordinating vendors, AV, catering, and setup "
            "crews to deliver flawless events."
        ),
        "responsibilities": [
            "Respond to event inquiries, conduct site tours, and prepare proposals and contracts",
            "Develop and manage banquet event orders (BEOs) as the single source of event truth",
            "Coordinate with catering, AV, décor, and external vendors to execute event logistics",
            "Conduct pre-event walkthroughs and ensure all setups meet client specifications",
            "Serve as on-site point of contact during events, managing timelines and resolving issues",
            "Reconcile event invoices and process post-event billing accurately",
            "Gather post-event feedback and maintain client relationships for repeat business",
        ],
        "requirements": [
            "2+ years of event planning or catering-sales experience in a hotel or venue",
            "Strong project-management and multitasking abilities",
            "Experience with event-management or catering software (Delphi, Tripleseat, or similar)",
            "Excellent written and verbal communication for client-facing interactions",
            "Ability to work evenings, weekends, and holidays as events demand",
        ],
        "preferred": [
            "CMP (Certified Meeting Professional) or similar designation",
            "Experience managing events for 200+ attendees",
            "Familiarity with AV production and hybrid event technology",
        ],
    },

    # ── Healthcare ─────────────────────────────────────────────────────────────

    "registered-nurse": {
        "summary": (
            "The Registered Nurse provides direct patient care in accordance with evidence-based "
            "practice, physician orders, and applicable nursing standards. You will assess patient "
            "conditions, administer medications, develop and monitor care plans, and collaborate "
            "with interdisciplinary teams to achieve optimal patient outcomes."
        ),
        "responsibilities": [
            "Perform comprehensive patient assessments and document findings in the EMR",
            "Administer medications and treatments per provider orders and the five rights of medication administration",
            "Develop, implement, and evaluate individualized nursing care plans",
            "Communicate patient status changes to physicians and care team members promptly",
            "Educate patients and families on conditions, medications, and discharge instructions",
            "Supervise and delegate tasks to LPN/LVN and CNA staff per scope of practice",
            "Maintain strict compliance with HIPAA, infection control, and Joint Commission standards",
        ],
        "requirements": [
            "Active and unrestricted RN license in the applicable state",
            "Associate's degree in Nursing (ADN) or Bachelor of Science in Nursing (BSN)",
            "Current BLS certification; ACLS preferred for acute care settings",
            "Strong clinical assessment and critical-thinking skills",
            "Proficiency with electronic medical record (EMR) systems",
        ],
        "preferred": [
            "BSN and 2+ years of clinical experience in the relevant specialty",
            "Specialty certification (CCRN, CEN, Med-Surg Certification, etc.)",
            "Experience with EPIC, Cerner, or equivalent EMR platform",
        ],
    },

    "lvn-lpn": {
        "summary": (
            "The Licensed Vocational Nurse (LVN) / Licensed Practical Nurse (LPN) provides "
            "direct patient care under the supervision of a Registered Nurse or physician. "
            "You will collect vitals, administer medications, perform wound care, and document "
            "all interventions accurately in the EMR."
        ),
        "responsibilities": [
            "Collect and record patient vital signs and basic health information",
            "Administer oral, topical, and injectable medications per scope of practice and provider orders",
            "Perform wound assessment, dressing changes, and basic wound care procedures",
            "Assist with patient admissions, transfers, and discharges",
            "Communicate patient concerns and changes in condition to supervising RN or physician",
            "Maintain accurate and timely documentation in the EMR",
            "Follow infection control, safety, and HIPAA compliance protocols",
        ],
        "requirements": [
            "Active and unrestricted LVN/LPN license in the applicable state",
            "Completion of an accredited LVN/LPN program",
            "Current BLS certification",
            "Ability to perform physical tasks including prolonged standing and lifting up to 50 lbs with assistance",
            "Strong attention to detail and documentation accuracy",
        ],
        "preferred": [
            "1+ year of LVN/LPN experience in a clinical or long-term care setting",
            "IV certification (where applicable by state)",
            "Familiarity with EMR platforms (EPIC, PointClickCare, etc.)",
        ],
    },

    "medical-assistant": {
        "summary": (
            "The Medical Assistant supports clinical and administrative operations in a physician "
            "office, clinic, or outpatient setting. You will room patients, document chief complaints "
            "in the EMR, perform phlebotomy and basic diagnostics, and assist providers with "
            "examinations — keeping the clinic running on time and at a high standard of care."
        ),
        "responsibilities": [
            "Room patients, obtain vital signs, and document reason for visit in the EMR prior to provider entry",
            "Assist providers during examinations and minor procedures",
            "Perform phlebotomy, EKGs, urinalysis, and other in-office diagnostic tests",
            "Prepare and administer medications and vaccinations per provider order and protocol",
            "Schedule follow-up appointments and coordinate referrals and prior authorizations",
            "Maintain exam-room supplies, equipment logs, and medication inventory",
            "Perform front-desk and clerical duties including patient check-in, phone triage, and insurance verification",
        ],
        "requirements": [
            "Medical Assistant diploma or certificate from an accredited program",
            "CMA (AAMA), RMA (AMT), or equivalent certification (or eligibility within 12 months of hire)",
            "Current BLS/CPR certification",
            "Proficiency with EMR software; experience with athenahealth, EPIC, or eClinicalWorks a plus",
            "Ability to maintain patient confidentiality in accordance with HIPAA",
        ],
        "preferred": [
            "1+ years of clinical medical assistant experience",
            "Bilingual skills to support diverse patient populations",
            "Experience with prior-authorization and insurance-verification workflows",
        ],
    },

    "cna": {
        "summary": (
            "The Certified Nursing Assistant (CNA) provides direct personal care to patients or "
            "residents under the supervision of licensed nursing staff. You will assist with "
            "activities of daily living (ADLs), monitor and document vital signs, and maintain a "
            "safe and supportive environment for those in your care."
        ),
        "responsibilities": [
            "Assist patients/residents with bathing, dressing, grooming, oral hygiene, and toileting",
            "Collect and document vital signs including blood pressure, pulse, respiration, and temperature",
            "Reposition patients as directed to prevent pressure injuries",
            "Assist with ambulation, transfers, and mobility using proper body mechanics and equipment",
            "Report changes in patient condition, behavior, or skin integrity to supervising RN/LPN",
            "Follow infection control protocols and maintain a clean care environment",
            "Document all care provided accurately and in a timely manner",
        ],
        "requirements": [
            "Active CNA certification in the applicable state",
            "Completion of a state-approved nursing assistant training program",
            "Current BLS/CPR certification",
            "Compassionate patient-care attitude and strong communication skills",
            "Ability to perform physically demanding tasks including lifting/transferring up to 50 lbs with assistance",
        ],
        "preferred": [
            "6+ months of CNA experience in a hospital, SNF, or home health setting",
            "Experience with memory care or behavioral health populations",
            "Bilingual language skills",
        ],
    },

    "phlebotomist": {
        "summary": (
            "The Phlebotomist collects blood and other specimens from patients for laboratory "
            "analysis. You will ensure proper patient identification, perform venipuncture and "
            "capillary collection with a high first-stick success rate, process and label specimens "
            "accurately, and maintain a calm, patient-centered environment."
        ),
        "responsibilities": [
            "Verify patient identity using two identifiers before every collection",
            "Perform venipuncture, capillary puncture, and other specimen collection techniques",
            "Label all specimens accurately at point of collection and process per laboratory protocol",
            "Package and transport specimens according to handling and temperature requirements",
            "Explain collection procedures to patients and manage patient anxiety effectively",
            "Maintain supply inventory, equipment logs, and collection station cleanliness",
            "Adhere to all infection control, safety, and HIPAA standards",
        ],
        "requirements": [
            "Phlebotomy certification (CPT-ASCP, NPA, or state equivalent) or completion of accredited phlebotomy program",
            "Current BLS/CPR certification",
            "Demonstrated high first-stick success rate",
            "Attention to detail and accuracy in specimen labeling and documentation",
            "Ability to work calmly with patients of all ages including pediatric patients",
        ],
        "preferred": [
            "1+ year of phlebotomy experience in a hospital, lab, or outpatient setting",
            "Experience with LIS (Laboratory Information System) software",
            "Bilingual skills",
        ],
    },

    "medical-receptionist": {
        "summary": (
            "The Medical Receptionist is the face of the practice and manages all front-office "
            "functions to ensure a smooth patient flow. You will greet patients, schedule and "
            "confirm appointments, verify insurance, collect copays, and maintain HIPAA-compliant "
            "patient records."
        ),
        "responsibilities": [
            "Greet patients and visitors courteously upon arrival and departure",
            "Schedule, confirm, and cancel patient appointments using the practice management system",
            "Verify insurance eligibility and obtain prior authorizations as required",
            "Collect copays, deductibles, and outstanding balances; post payments accurately",
            "Maintain and update patient demographic and insurance information in the EMR",
            "Answer multi-line phone system, triage calls, and relay accurate messages to clinical staff",
            "Scan, file, and manage medical records in accordance with HIPAA privacy regulations",
        ],
        "requirements": [
            "High school diploma or equivalent",
            "1+ year of medical front-office or customer-service experience",
            "Familiarity with insurance verification, CPT and ICD-10 codes, and billing basics",
            "Proficiency with EMR/practice management software (athenahealth, NextGen, or similar)",
            "Strong interpersonal skills and patient-first attitude",
        ],
        "preferred": [
            "Medical office administration certificate or associate's degree",
            "Bilingual communication skills",
            "Experience with referral coordination and prior authorization workflows",
        ],
    },

    "behavioral-health-technician": {
        "summary": (
            "The Behavioral Health Technician (BHT) provides direct support and supervision to "
            "patients in psychiatric, substance-use, or behavioral health treatment settings. "
            "You will monitor patient safety, facilitate therapeutic activities, document observations, "
            "and assist the clinical team in delivering trauma-informed care."
        ),
        "responsibilities": [
            "Conduct regular patient observations and document behavior, mood, and safety status",
            "Maintain a safe therapeutic milieu and intervene during behavioral escalations using approved de-escalation techniques",
            "Assist patients with daily living activities and group participation",
            "Transport patients to/from appointments, activities, and therapeutic groups as assigned",
            "Complete admissions intake documentation, inventory of personal property, and orientation",
            "Implement individualized behavior support plans under clinical supervision",
            "Communicate relevant patient observations to the nursing and clinical team",
        ],
        "requirements": [
            "High school diploma or equivalent; Bachelor's degree in psychology or related field a plus",
            "Completion of BHT training or Mental Health Worker certification (state-specific requirements may apply)",
            "Current CPR/BLS certification; de-escalation or CPI training preferred",
            "Empathy, patience, and strong boundary-setting skills",
            "Ability to work in a high-acuity environment including nights and weekends",
        ],
        "preferred": [
            "1+ year of experience in an inpatient psychiatric, residential, or substance-use treatment setting",
            "Knowledge of motivational interviewing or cognitive behavioral techniques",
            "Bilingual communication skills",
        ],
    },

    "home-health-aide": {
        "summary": (
            "The Home Health Aide provides non-medical personal care and companionship to clients "
            "in their homes, supporting their independence and quality of life. You will assist "
            "with activities of daily living, light housekeeping, medication reminders, and basic "
            "vital-sign monitoring under the direction of a supervising nurse or care coordinator."
        ),
        "responsibilities": [
            "Assist clients with bathing, dressing, grooming, oral hygiene, and toileting",
            "Prepare nutritious meals and snacks according to dietary restrictions and care plans",
            "Perform light housekeeping, laundry, and household organization tasks",
            "Monitor and record vital signs (temperature, pulse, blood pressure) as directed",
            "Provide medication reminders and assist with self-administered medications per agency protocol",
            "Accompany clients to medical appointments and community activities",
            "Document care provided and report changes in client condition to the supervising nurse",
        ],
        "requirements": [
            "Home Health Aide certificate or HHA competency test completion (state requirements apply)",
            "Current CPR/BLS certification",
            "Valid driver's license and reliable transportation",
            "Compassionate, patient, and dependable work style",
            "Ability to perform physical tasks including lifting and transferring clients with assistance",
        ],
        "preferred": [
            "6+ months of HHA or personal care aide experience",
            "Experience supporting clients with dementia, Parkinson's, or post-surgical recovery",
            "Bilingual language skills",
        ],
    },

    # ── Retail ─────────────────────────────────────────────────────────────────

    "retail-sales-associate": {
        "summary": (
            "The Retail Sales Associate delivers an exceptional customer experience on the sales "
            "floor by greeting shoppers, providing product knowledge, and closing sales. You will "
            "maintain merchandising standards, process transactions accurately, and support loss "
            "prevention through awareness and adherence to policy."
        ),
        "responsibilities": [
            "Welcome customers, identify needs, and recommend products using consultative selling techniques",
            "Operate the POS system to process cash, credit, and digital payment transactions",
            "Execute merchandising standards including sizing, folding, and replenishment",
            "Assist with inventory counts, receiving shipments, and organizing stockroom",
            "Handle returns, exchanges, and customer complaints professionally",
            "Maintain awareness of shoplifting indicators and report concerns to management",
            "Meet individual and team sales goals as set by store leadership",
        ],
        "requirements": [
            "High school diploma or equivalent",
            "1+ year of retail or customer-service experience",
            "Strong communication and interpersonal skills",
            "Ability to stand for extended periods and lift up to 30 lbs",
            "Availability to work evenings, weekends, and peak retail seasons",
        ],
        "preferred": [
            "Product knowledge in the store's merchandise category",
            "Experience with a specific POS platform (Square, Lightspeed, Shopify POS)",
            "Proven track record of meeting sales metrics",
        ],
    },

    "cashier": {
        "summary": (
            "The Cashier processes customer transactions quickly and accurately while providing "
            "friendly service. You will handle cash and electronic payments, assist with returns, "
            "and ensure the checkout area is organized and stocked."
        ),
        "responsibilities": [
            "Scan and ring up customer purchases accurately using the POS system",
            "Process cash, credit/debit card, check, and digital payment methods",
            "Issue receipts, refunds, change, and vouchers per company policy",
            "Verify customer identification for age-restricted products as required",
            "Bag or package merchandise carefully to prevent damage",
            "Maintain a clean, organized checkout lane and restock impulse-buy areas",
            "Balance cash drawer at the start and end of each shift",
        ],
        "requirements": [
            "High school diploma or equivalent",
            "Basic math skills and comfort handling cash",
            "Reliable, punctual, and customer-focused work ethic",
            "Ability to stand for an entire shift",
            "Availability to work varied shifts including weekends and holidays",
        ],
        "preferred": [
            "Prior cashier or retail experience",
            "Experience with specific POS systems",
            "Bilingual communication skills",
        ],
    },

    "store-manager": {
        "summary": (
            "The Store Manager owns the full performance of a retail location — from people "
            "management and scheduling to P&L oversight and brand execution. You will hire, "
            "develop, and retain a high-performing team, drive sales results, and ensure the "
            "store operates in compliance with all company and regulatory standards."
        ),
        "responsibilities": [
            "Oversee all daily store operations including opening/closing procedures and cash management",
            "Recruit, interview, hire, onboard, and train store associates and supervisors",
            "Build and manage team schedules to align labor hours with sales volume and budget",
            "Analyze P&L reports, monitor shrink, and implement action plans to hit financial targets",
            "Drive sales and conversion through coaching, floor presence, and customer engagement",
            "Enforce visual merchandising and product placement standards from corporate",
            "Handle escalated customer concerns and ensure consistent service standards",
            "Conduct performance reviews, coaching sessions, and disciplinary actions as needed",
        ],
        "requirements": [
            "3+ years of retail management experience, including full P&L ownership",
            "Demonstrated success in team development and performance management",
            "Strong analytical skills and comfort with sales reporting tools",
            "Excellent communication and leadership skills",
            "Flexibility to work varied shifts including evenings, weekends, and holidays",
        ],
        "preferred": [
            "Experience managing a multi-million-dollar volume location",
            "Bachelor's degree in Business, Retail Management, or related field",
            "Familiarity with workforce management software (Kronos, Workday)",
        ],
    },

    "assistant-store-manager": {
        "summary": (
            "The Assistant Store Manager supports the Store Manager in all operational and people "
            "functions. You will lead shifts, open and close the store, train team members, and "
            "serve as acting store manager in the SM's absence. A key focus is developing team "
            "members while maintaining store KPIs and brand standards."
        ),
        "responsibilities": [
            "Lead the sales floor and manage team performance during assigned shifts",
            "Execute opening and closing procedures including cash reconciliation and security checks",
            "Assist in recruiting, onboarding, and training new associates",
            "Monitor and communicate daily, weekly, and monthly sales KPIs to the team",
            "Resolve customer issues and complaints in a fair and brand-consistent manner",
            "Execute floor sets, promotional changes, and visual merchandising directives",
            "Support inventory management including cycle counts and shrink prevention",
        ],
        "requirements": [
            "2+ years of retail experience including at least 1 year in a supervisory role",
            "Strong coaching and team-motivation skills",
            "Proven ability to meet and exceed sales and service metrics",
            "Availability to work varied shifts, weekends, and holidays",
            "Basic proficiency with retail reporting and scheduling tools",
        ],
        "preferred": [
            "Experience with P&L review and labor management",
            "Readiness for promotion to Store Manager within 12 months",
            "Brand-specific product knowledge",
        ],
    },

    "visual-merchandiser": {
        "summary": (
            "The Visual Merchandiser brings the brand to life by creating compelling window and "
            "floor displays that drive traffic and conversion. You will execute planograms, develop "
            "creative installations, and ensure all visual standards are maintained across the store."
        ),
        "responsibilities": [
            "Design and install window displays, mannequin styling, and floor fixtures to brand standards",
            "Interpret and execute planograms and visual directives from corporate",
            "Partner with the Store Manager on product placement strategies to maximize sell-through",
            "Adapt seasonal and promotional displays on schedule",
            "Conduct regular store walks to identify and correct visual inconsistencies",
            "Train store associates on basic folding, sizing, and display maintenance",
            "Photograph finished displays for corporate reporting",
        ],
        "requirements": [
            "2+ years of visual merchandising or display experience in retail",
            "Strong aesthetic sensibility and creative problem-solving skills",
            "Ability to interpret and execute corporate visual direction",
            "Physical ability to lift fixtures, climb ladders, and work in stockroom environments",
            "Portfolio of past display work preferred",
        ],
        "preferred": [
            "Degree or certificate in Fashion Merchandising, Visual Communications, or related field",
            "Experience with Adobe Creative Suite for creating display schematics",
            "Multi-location or field visual merchandising experience",
        ],
    },

    "stock-associate": {
        "summary": (
            "The Stock Associate ensures the sales floor and stockroom are organized, fully "
            "replenished, and accurately inventoried. You will receive and process shipments, "
            "restock merchandise, and support the store team in maintaining a neat, shoppable "
            "environment."
        ),
        "responsibilities": [
            "Receive, open, and process incoming merchandise shipments accurately",
            "Replenish sales floor product based on sell-through and visual standards",
            "Organize and maintain a logical, efficient stockroom layout",
            "Conduct cycle counts and assist with full physical inventory events",
            "Return go-backs and pulls to their correct stockroom locations",
            "Prepare outbound transfers and damage claims per company procedure",
            "Support floor associates during peak traffic periods",
        ],
        "requirements": [
            "High school diploma or equivalent",
            "Ability to lift up to 50 lbs and stand for extended periods",
            "Organized and detail-oriented work style",
            "Availability to work early-morning stocking shifts, weekends, and holidays",
            "Basic math skills for inventory tracking",
        ],
        "preferred": [
            "Prior retail stock or warehouse associate experience",
            "Familiarity with inventory management software",
            "Forklift or pallet jack certification",
        ],
    },

    # ── Restaurants & QSR ──────────────────────────────────────────────────────

    "line-cook": {
        "summary": (
            "The Line Cook prepares and plates menu items to recipe specifications in a high-volume "
            "kitchen environment. You will manage your station from prep through service, maintain "
            "food safety standards, and work in close coordination with the BOH team to deliver "
            "consistent quality under pressure."
        ),
        "responsibilities": [
            "Set up and break down your station according to prep lists and mise en place standards",
            "Prepare and cook menu items to recipe specifications and plating standards",
            "Monitor portion control, food quality, and presentation throughout service",
            "Maintain station cleanliness and follow FIFO labeling and rotation protocols",
            "Communicate ticket times and adjustments with expo and kitchen team",
            "Perform daily cleaning tasks including degreasing, sweeping, and equipment sanitation",
            "Comply with all food safety standards and assist with maintaining a ServSafe-certified environment",
        ],
        "requirements": [
            "1+ year of line cook or equivalent kitchen experience",
            "Proficiency with knife skills and commercial kitchen equipment",
            "ServSafe Food Handler certification (or ability to obtain within 30 days of hire)",
            "Ability to stand for extended periods and work in hot, fast-paced conditions",
            "Availability to work nights, weekends, and holidays",
        ],
        "preferred": [
            "Culinary diploma from an accredited program",
            "Experience in a high-volume or fine-dining kitchen",
            "Cross-training across multiple stations",
        ],
    },

    "prep-cook": {
        "summary": (
            "The Prep Cook supports culinary operations by completing advance preparation tasks "
            "that allow line cooks to execute service efficiently. You will handle knife work, "
            "batch cooking, and stock and sauce production while upholding the highest standards "
            "of food safety and sanitation."
        ),
        "responsibilities": [
            "Complete daily prep lists including cutting, portioning, and marinating proteins, produce, and dairy",
            "Prepare stocks, sauces, soups, and components per batch recipes",
            "Label, date, and store all prepped items following FIFO and temperature-control standards",
            "Maintain the cleanliness of prep areas, tools, and walk-in coolers/freezers",
            "Assist line cooks with restocking during service as directed",
            "Notify chef or sous chef of low inventory or quality concerns",
        ],
        "requirements": [
            "Solid knife skills and basic cooking technique",
            "ServSafe Food Handler certification (or ability to obtain within 30 days)",
            "Ability to stand, lift up to 50 lbs, and work in fast-paced kitchen conditions",
            "Reliable and organized with strong attention to recipe accuracy",
            "Availability to work early-morning and weekend shifts",
        ],
        "preferred": [
            "1+ year of prep or entry-level kitchen experience",
            "Culinary school enrollment or completion",
            "Familiarity with a variety of cuisine styles",
        ],
    },

    "server": {
        "summary": (
            "The Server delivers an exceptional dining experience from greeting through farewell. "
            "You will guide guests through menus, manage orders accurately in the POS system, "
            "handle payments, and upsell thoughtfully — all while maintaining a warm, attentive "
            "presence that turns first-time guests into regulars."
        ),
        "responsibilities": [
            "Greet guests promptly, present menus, and provide knowledgeable menu recommendations",
            "Take and enter food and beverage orders accurately into the POS",
            "Communicate special dietary needs and allergen information to the kitchen",
            "Deliver food and beverage items in a timely, organized manner",
            "Monitor and manage table satisfaction throughout the dining experience",
            "Process cash and electronic payments accurately and issue receipts",
            "Complete opening and closing side work including restocking and polishing",
        ],
        "requirements": [
            "1+ year of full-service restaurant serving experience",
            "Knowledge of food, wine, and cocktail pairings",
            "Allergen awareness and ability to communicate modifications to the kitchen",
            "Proficiency with POS systems (Toast, Aloha, or similar)",
            "Availability to work nights, weekends, and holidays",
        ],
        "preferred": [
            "RBS (Responsible Beverage Service) or TIPS certification",
            "Fine-dining or high-volume service experience",
            "Bilingual communication skills",
        ],
    },

    "bartender": {
        "summary": (
            "The Bartender crafts cocktails, manages the bar environment, and provides exceptional "
            "guest service. You will maintain product knowledge across spirits, wine, and beer, "
            "serve alcohol responsibly, track inventory, and create an engaging bar atmosphere that "
            "drives repeat visits."
        ),
        "responsibilities": [
            "Prepare and serve cocktails, beer, wine, and non-alcoholic beverages to recipe and quality standards",
            "Engage guests in friendly conversation and create a welcoming bar experience",
            "Check identification and refuse service to intoxicated or underage guests",
            "Manage bar inventory, track usage, and participate in weekly/monthly bar counts",
            "Maintain cleanliness of the bar area, glassware, and equipment throughout shift",
            "Process orders and payments via POS with accuracy",
            "Collaborate with kitchen on food-pairing recommendations and timely ticket delivery",
        ],
        "requirements": [
            "2+ years of bartending experience in a full-service restaurant or bar",
            "TIPS, ServSafe Alcohol, or RBS certification",
            "Comprehensive knowledge of spirits, cocktail techniques, and current beverage trends",
            "Strong multitasking ability in a high-volume environment",
            "Availability to work nights, weekends, and late-night shifts",
        ],
        "preferred": [
            "Craft cocktail or specialty bar program experience",
            "Experience developing seasonal cocktail menus",
            "Wine or spirits certification (WSET, CMS, etc.)",
        ],
    },

    "host": {
        "summary": (
            "The Host/Hostess is the first and last impression of the dining experience. You will "
            "manage reservations, greet guests, quote wait times accurately, and coordinate seating "
            "to maximize dining-room flow — all while maintaining a warm, polished presence that "
            "sets the tone for the entire meal."
        ),
        "responsibilities": [
            "Welcome guests upon arrival and manage the door during peak periods",
            "Manage reservation system and waitlist using digital tools (OpenTable, Resy, Yelp)",
            "Provide accurate wait-time estimates and communicate status updates to waiting guests",
            "Coordinate table assignments with servers and managers to balance floor workload",
            "Escort guests to tables, present menus, and introduce server",
            "Answer phones, take reservations, and respond to guest inquiries",
            "Maintain the host stand and lobby area in an organized and welcoming state",
        ],
        "requirements": [
            "Prior host, front-of-house, or customer-service experience",
            "Strong organizational skills and composure during high-volume periods",
            "Professional appearance and warm, attentive communication style",
            "Familiarity with reservation management software",
            "Availability to work evenings, weekends, and holidays",
        ],
        "preferred": [
            "Experience in a high-volume or fine-dining environment",
            "Bilingual communication skills",
            "Basic knowledge of restaurant operations",
        ],
    },

    "dishwasher": {
        "summary": (
            "The Dishwasher is an essential part of the kitchen team, ensuring clean, sanitized "
            "dishware, cookware, and utensils are always available for service. You will maintain "
            "the dish station, support kitchen cleanliness, and assist with basic food prep as "
            "needed."
        ),
        "responsibilities": [
            "Wash and sanitize all dishes, glassware, silverware, pots, and pans to health code standards",
            "Operate commercial dishwashing equipment safely and effectively",
            "Return clean items to their designated stations in the kitchen and bar",
            "Remove trash and maintain cleanliness of dish station and back-of-house areas",
            "Assist with basic prep tasks (peeling, chopping) as directed by the kitchen team",
            "Restock supplies (dish soap, sanitizer, gloves) at the dish station",
        ],
        "requirements": [
            "Ability to stand for an entire shift and lift up to 50 lbs",
            "Reliability and strong work ethic in a physically demanding environment",
            "Ability to work in a hot, loud, fast-paced kitchen",
            "Availability to work evenings, weekends, and holidays",
        ],
        "preferred": [
            "Prior dish or kitchen experience",
            "Food handler card or ability to obtain one within 30 days",
            "Interest in learning and growing within the culinary field",
        ],
    },

    "shift-leader": {
        "summary": (
            "The Shift Leader oversees operations during an assigned shift in a restaurant or QSR "
            "environment. You will manage the team on the floor, ensure food safety compliance, "
            "handle cash and deposits, and deliver consistent guest service — serving as the "
            "on-shift authority in the absence of the General Manager."
        ),
        "responsibilities": [
            "Open or close the restaurant following established checklists and procedures",
            "Direct team member tasks during the shift to meet speed-of-service and quality goals",
            "Count and reconcile cash drawers and complete daily deposit",
            "Monitor food safety compliance including temperatures, handwashing, and sanitation",
            "Address guest complaints and resolve service issues within established authority",
            "Complete shift paperwork including waste logs, labor tracking, and incident reports",
            "Provide on-the-job coaching and training feedback to team members",
        ],
        "requirements": [
            "1+ year of QSR, fast-casual, or food-service experience",
            "Prior supervisory or lead experience",
            "ServSafe Food Handler or Food Manager certification (or ability to obtain)",
            "Strong organizational and communication skills",
            "Availability to work opening, closing, and weekend shifts",
        ],
        "preferred": [
            "Experience with restaurant POS and back-of-house software",
            "Completed or pursuing a food-service management certificate",
            "Bilingual skills",
        ],
    },

    "general-manager-restaurant": {
        "summary": (
            "The Restaurant General Manager leads all aspects of restaurant operations to maximize "
            "guest satisfaction, team performance, and financial results. You will control food and "
            "labor costs, develop your team, enforce brand and safety standards, and build a culture "
            "of hospitality and accountability."
        ),
        "responsibilities": [
            "Direct all front-of-house and back-of-house operations to achieve quality and speed-of-service goals",
            "Manage P&L by controlling food cost, labor cost, and operating expenses to budget",
            "Recruit, interview, hire, onboard, and develop management and hourly team members",
            "Build and post schedules that align labor hours with forecasted volume",
            "Maintain brand standards, food safety compliance, and health department readiness",
            "Handle escalated guest concerns and ensure service recovery exceeds expectations",
            "Conduct regular performance reviews, coaching sessions, and disciplinary actions",
            "Report operational and financial results to area or district leadership",
        ],
        "requirements": [
            "3+ years of restaurant management experience, including P&L responsibility",
            "ServSafe Food Manager certification",
            "Demonstrated success in team development and retention",
            "Strong financial acumen and comfort with restaurant reporting tools",
            "Availability to work varied shifts including nights, weekends, and holidays",
        ],
        "preferred": [
            "Experience managing a high-volume ($1M+ annual revenue) location",
            "Multi-unit or franchise operations exposure",
            "Bachelor's degree in Hospitality Management or related field",
        ],
    },

    "delivery-driver": {
        "summary": (
            "The Delivery Driver represents the brand at the customer's door and ensures food "
            "arrives on time, at the correct temperature, and in perfect condition. You will manage "
            "your delivery route efficiently, handle payments where applicable, and maintain your "
            "vehicle in safe operating condition."
        ),
        "responsibilities": [
            "Pick up and deliver food orders to customers on schedule and with care",
            "Verify order accuracy before departure from the restaurant",
            "Use GPS and routing tools to navigate efficiently and minimize delivery times",
            "Collect cash or digital payments from customers as required",
            "Maintain vehicle cleanliness and conduct daily safety pre-checks",
            "Communicate delays or issues to dispatch or restaurant management promptly",
            "Follow all food safety and temperature-maintenance guidelines during transport",
        ],
        "requirements": [
            "Valid driver's license with a clean motor vehicle record",
            "Reliable personal vehicle with current registration and insurance (for driver's own vehicle roles)",
            "Smartphone proficiency for routing and delivery management apps",
            "Customer-service mindset and professional demeanor",
            "Ability to lift and carry food bags up to 30 lbs",
        ],
        "preferred": [
            "Food handler certification or ability to obtain",
            "Experience with restaurant delivery platforms (DoorDash, Uber Eats, proprietary app)",
            "Knowledge of local streets and neighborhoods",
        ],
    },

    # ── Construction & Trades ─────────────────────────────────────────────────

    "electrician": {
        "summary": (
            "The Electrician installs, maintains, and repairs electrical systems in residential, "
            "commercial, or industrial settings. You will read blueprints and wiring diagrams, "
            "ensure compliance with the NEC and local codes, troubleshoot faults, and perform "
            "work safely at all times."
        ),
        "responsibilities": [
            "Install, maintain, and repair electrical wiring, fixtures, equipment, and controls",
            "Read and interpret blueprints, schematics, and electrical diagrams",
            "Test and troubleshoot electrical systems using meters, oscilloscopes, and diagnostic tools",
            "Ensure all work complies with the National Electrical Code (NEC) and applicable local codes",
            "Collaborate with general contractors, project managers, and inspectors on project requirements",
            "Complete material take-offs and assist with project scheduling",
            "Maintain a safe jobsite and adhere to OSHA electrical safety standards",
        ],
        "requirements": [
            "Journeyman Electrician license in applicable state (or Apprentice with equivalent experience)",
            "3+ years of commercial or industrial electrical experience",
            "Proficiency with NEC code compliance and permit processes",
            "OSHA 10 certification (OSHA 30 preferred)",
            "Ability to lift up to 50 lbs and work in confined spaces, at heights, and in varied weather",
        ],
        "preferred": [
            "Master Electrician license",
            "Experience with industrial motor controls, PLC systems, or solar/battery installations",
            "First Aid/CPR certification",
        ],
    },

    "plumber": {
        "summary": (
            "The Plumber installs, services, and repairs plumbing systems in new construction "
            "and existing residential or commercial structures. You will interpret blueprints, "
            "diagnose system issues, ensure code compliance, and deliver reliable craftsmanship "
            "on every job."
        ),
        "responsibilities": [
            "Install, repair, and maintain pipes, fixtures, water heaters, and drainage systems",
            "Read and interpret blueprints, isometric drawings, and plumbing layouts",
            "Diagnose system failures using pressure tests, leak detection, and camera inspection tools",
            "Ensure all work complies with local plumbing codes and obtain permits as required",
            "Coordinate with general contractors and inspection authorities on project timelines",
            "Manage material requirements and maintain a clean, organized work vehicle",
            "Respond to service calls and emergency repairs as dispatched",
        ],
        "requirements": [
            "Journeyman Plumber license in applicable state",
            "3+ years of plumbing experience in residential, commercial, or service settings",
            "Knowledge of local plumbing codes and permit processes",
            "OSHA 10 certification",
            "Valid driver's license",
        ],
        "preferred": [
            "Master Plumber license",
            "Experience with hydronic heating, medical gas, or backflow prevention systems",
            "EPA 608 Universal certification",
        ],
    },

    "hvac-technician": {
        "summary": (
            "The HVAC Technician installs, services, and repairs heating, ventilation, air "
            "conditioning, and refrigeration systems. You will handle refrigerant management, "
            "diagnose mechanical and electrical faults, ensure code compliance, and deliver "
            "outstanding technical service to commercial and/or residential clients."
        ),
        "responsibilities": [
            "Install, start up, and commission HVAC/R equipment per manufacturer and code specifications",
            "Perform preventive maintenance on heating, cooling, and ventilation systems",
            "Diagnose and repair mechanical, electrical, and control-system failures",
            "Handle refrigerants in accordance with EPA Section 608 regulations",
            "Review service history and document all work completed in the service management system",
            "Educate clients on equipment operation, maintenance, and efficiency improvements",
            "Maintain company vehicle and stock of commonly used parts and tools",
        ],
        "requirements": [
            "EPA 608 Universal certification (Type I/II/III)",
            "3+ years of HVAC/R installation or service experience",
            "Proficiency with electrical troubleshooting tools and HVAC diagnostic equipment",
            "Valid driver's license with a clean record",
            "Ability to work in confined spaces, at heights, and in extreme temperatures",
        ],
        "preferred": [
            "NATE (North American Technician Excellence) certification",
            "Experience with Building Automation Systems (BAS/BMS)",
            "OSHA 10 or 30 certification",
        ],
    },

    "carpenter": {
        "summary": (
            "The Carpenter performs framing, finish carpentry, and cabinetry work on residential "
            "and commercial construction projects. You will read blueprints, select appropriate "
            "materials, use hand and power tools safely, and deliver high-quality craftsmanship "
            "on schedule."
        ),
        "responsibilities": [
            "Perform rough framing, sheathing, and structural wood assembly per blueprints",
            "Install doors, windows, trim, cabinets, and finish carpentry elements",
            "Read and interpret construction drawings and cut sheets",
            "Select, measure, cut, and shape materials with precision",
            "Collaborate with subcontractors and trades to coordinate installation sequences",
            "Maintain a clean, organized, and safe work area at all times",
            "Complete work in compliance with local building codes and OSHA safety standards",
        ],
        "requirements": [
            "3+ years of carpentry experience in residential or commercial construction",
            "Proficiency with power tools, nail guns, and basic measuring equipment",
            "Blueprint reading skills",
            "OSHA 10 certification",
            "Ability to lift up to 50 lbs and work at heights using ladders and scaffolding",
        ],
        "preferred": [
            "Journeyman Carpenter union card or equivalent certification",
            "Finish carpentry or millwork specialization",
            "First Aid/CPR certification",
        ],
    },

    "project-superintendent": {
        "summary": (
            "The Project Superintendent is the on-site authority for construction project delivery. "
            "You will coordinate all trades, maintain the project schedule, enforce safety "
            "compliance, and serve as the primary point of contact for owners, architects, and "
            "inspectors — ensuring the project finishes on time, on budget, and defect-free."
        ),
        "responsibilities": [
            "Direct day-to-day field operations and coordinate subcontractor and material schedules",
            "Maintain and update the master construction schedule; identify and resolve sequencing conflicts",
            "Conduct daily site walks to monitor quality, safety, and progress against milestones",
            "Serve as the primary site contact for owners, architects, engineers, and inspectors",
            "Run weekly owner-architect-contractor (OAC) and subcontractor coordination meetings",
            "Review and approve subcontractor work for quality and code compliance before concealment",
            "Investigate and document all incidents, near-misses, and non-conformances",
        ],
        "requirements": [
            "7+ years of commercial construction field experience, including 3+ years as superintendent",
            "Strong knowledge of all trades, construction sequences, and building codes",
            "Proficiency with construction management software (Procore, Bluebeam, MS Project)",
            "OSHA 30 certification",
            "Valid driver's license",
        ],
        "preferred": [
            "LEED AP or equivalent sustainability credential",
            "Experience on projects valued at $10M or more",
            "First Aid/AED/CPR certification",
        ],
    },

    "safety-officer": {
        "summary": (
            "The Safety Officer develops, implements, and enforces workplace health and safety "
            "programs to protect employees, subcontractors, and the public. You will conduct "
            "inspections, lead incident investigations, deliver training, and ensure full "
            "compliance with OSHA regulations and company safety policy."
        ),
        "responsibilities": [
            "Develop and update the site-specific Health and Safety Plan (HASP) and Job Safety Analyses (JSAs)",
            "Conduct regular site inspections and audits to identify and correct hazardous conditions",
            "Lead incident, near-miss, and first-aid investigations; complete required reporting",
            "Deliver OSHA-compliant safety orientations, toolbox talks, and specialized training",
            "Maintain all required safety records including training logs, inspection reports, and OSHA 300 logs",
            "Liaise with OSHA, insurance carriers, and clients on safety compliance matters",
            "Recommend and monitor corrective action plans to close identified gaps",
        ],
        "requirements": [
            "Bachelor's degree in Occupational Safety, Industrial Hygiene, or related field (or equivalent experience)",
            "OSHA 30 construction or general industry certification",
            "3+ years of EHS or safety-officer experience in construction, manufacturing, or industrial settings",
            "Strong knowledge of OSHA 1910 and 1926 standards",
            "Excellent communication and training facilitation skills",
        ],
        "preferred": [
            "Certified Safety Professional (CSP) or Associate Safety Professional (ASP) designation",
            "Experience with ISO 45001 or OHSAS 18001 management systems",
            "First Aid/CPR instructor certification",
        ],
    },

    # ── Manufacturing & Warehouse ──────────────────────────────────────────────

    "production-operator": {
        "summary": (
            "The Production Operator runs, monitors, and maintains manufacturing equipment to "
            "produce goods that meet quality and output targets. You will follow standardized work "
            "procedures, perform quality checks, and participate in lean/continuous improvement "
            "activities to maximize efficiency and reduce waste."
        ),
        "responsibilities": [
            "Set up, operate, and monitor production machinery per work instructions and production schedules",
            "Inspect finished products against quality standards and document findings",
            "Identify and report equipment malfunctions, quality deviations, or safety hazards",
            "Perform basic first-level preventive maintenance and machine cleaning tasks",
            "Maintain accurate production logs, counts, and downtime records",
            "Follow all GMP, ISO, and company safety standards",
            "Participate in 5S, kaizen, and continuous improvement initiatives",
        ],
        "requirements": [
            "High school diploma or GED",
            "1+ year of manufacturing or production experience",
            "Ability to lift up to 50 lbs, stand for extended periods, and work in a manufacturing environment",
            "Basic mechanical aptitude and attention to quality detail",
            "Availability to work assigned shift including overtime as required",
        ],
        "preferred": [
            "Lean Manufacturing or Six Sigma Yellow Belt training",
            "Experience in a regulated manufacturing environment (food, medical device, pharma)",
            "Forklift or scissor-lift certification",
        ],
    },

    "forklift-operator": {
        "summary": (
            "The Forklift Operator safely moves materials and product throughout the warehouse "
            "or production floor using sit-down, stand-up, reach, or order-picker equipment. "
            "You will maintain accurate inventory locations, perform equipment inspections, and "
            "support a safe, efficient warehouse operation."
        ),
        "responsibilities": [
            "Operate sit-down counterbalance, reach truck, or order-picker forklift to move product",
            "Complete pre-shift equipment inspections and report deficiencies to maintenance",
            "Place, retrieve, and transfer pallets accurately based on WMS direction or verbal instruction",
            "Assist with receiving, put-away, and outbound staging activities",
            "Perform cycle counts and physical inventory tasks",
            "Maintain clear aisles, floor markings, and organized rack locations",
            "Adhere strictly to OSHA forklift safety standards and speed limits",
        ],
        "requirements": [
            "Current OSHA-compliant forklift certification for applicable equipment types",
            "1+ year of forklift operation in a warehouse or distribution center",
            "Clean safety record and demonstrated commitment to forklift safety protocols",
            "Ability to lift up to 50 lbs and work in varying temperature environments",
            "Availability to work assigned shifts including weekends and overtime",
        ],
        "preferred": [
            "Experience with WMS platforms (Manhattan, SAP WM, or similar)",
            "Certification on multiple forklift types (sit-down, reach, order picker)",
            "OSHA 10 General Industry certification",
        ],
    },

    "warehouse-associate": {
        "summary": (
            "The Warehouse Associate performs core fulfillment operations including receiving, "
            "picking, packing, and shipping. You will use RF scanners and WMS systems to process "
            "transactions accurately and efficiently, supporting the distribution center's throughput "
            "and on-time delivery goals."
        ),
        "responsibilities": [
            "Pick orders accurately from warehouse locations using RF scanner and WMS",
            "Pack outbound orders to shipping standards and apply correct labels",
            "Receive inbound freight, verify counts against purchase orders, and putaway to assigned locations",
            "Perform cycle counts and assist with physical inventory events",
            "Keep work area clean and organized per 5S standards",
            "Operate manual pallet jacks and hand trucks safely",
            "Report discrepancies, damaged goods, and safety concerns promptly",
        ],
        "requirements": [
            "High school diploma or GED",
            "Ability to lift up to 50 lbs repetitively and stand for an entire shift",
            "Basic computer and RF scanner proficiency",
            "Attention to detail and accuracy in order processing",
            "Availability to work assigned shifts including weekends and seasonal overtime",
        ],
        "preferred": [
            "1+ year of warehouse or distribution-center experience",
            "Familiarity with WMS software (SAP, Manhattan, or equivalent)",
            "Forklift or pallet-jack certification",
        ],
    },

    "shipping-receiving-clerk": {
        "summary": (
            "The Shipping & Receiving Clerk manages the documentation, processing, and "
            "tracking of all inbound and outbound freight. You will coordinate with carriers, "
            "verify shipment accuracy, maintain inventory transaction records, and resolve "
            "discrepancies promptly to keep the supply chain flowing."
        ),
        "responsibilities": [
            "Process inbound receipts by verifying quantities, conditions, and purchase orders in the ERP/WMS",
            "Prepare outbound shipments including packing lists, bills of lading (BOLs), and carrier labels",
            "Schedule carrier pickups and communicate tracking information to internal stakeholders",
            "Resolve discrepancies between POs, packing slips, and physical counts",
            "Maintain shipping/receiving logs and file freight documentation accurately",
            "Coordinate with purchasing, operations, and customer service on order status",
            "Follow proper procedures for hazardous materials documentation where applicable",
        ],
        "requirements": [
            "High school diploma or equivalent",
            "2+ years of shipping/receiving, logistics, or supply-chain experience",
            "Proficiency with ERP or WMS software (SAP, Oracle, NetSuite, or similar)",
            "Strong attention to detail and document accuracy",
            "Ability to lift up to 50 lbs and operate a manual pallet jack",
        ],
        "preferred": [
            "Associate's degree in Logistics, Supply Chain, or Business",
            "Experience with international freight and customs documentation",
            "Forklift certification",
        ],
    },

    "maintenance-technician": {
        "summary": (
            "The Maintenance Technician performs preventive and reactive maintenance on "
            "manufacturing or facility equipment to maximize uptime and equipment life. You will "
            "troubleshoot mechanical, electrical, hydraulic, and pneumatic systems and work "
            "closely with production to minimize unplanned downtime."
        ),
        "responsibilities": [
            "Execute the preventive maintenance schedule for assigned equipment and systems",
            "Diagnose and repair mechanical, electrical, hydraulic, and pneumatic failures",
            "Document all maintenance activities and findings in the CMMS",
            "Respond to equipment breakdowns and collaborate with production to reduce downtime",
            "Order and manage spare parts inventory for critical assets",
            "Assist with installation, commissioning, and relocation of production equipment",
            "Follow all LOTO, confined-space, and electrical safety procedures",
        ],
        "requirements": [
            "3+ years of maintenance experience in a manufacturing or industrial environment",
            "Proficiency in electrical troubleshooting (reading schematics, using a multimeter, basic PLC knowledge)",
            "Mechanical skills across motors, gearboxes, conveyors, and pneumatic systems",
            "OSHA 10 certification",
            "Ability to lift up to 50 lbs and work in physically demanding environments",
        ],
        "preferred": [
            "Industrial Maintenance Mechanic certification or equivalent trade credential",
            "Experience with CMMS systems (SAP PM, Maximo, Fiix)",
            "Welding (MIG/TIG) skills",
        ],
    },

    "quality-inspector": {
        "summary": (
            "The Quality Inspector verifies that products, components, or processes meet "
            "established specifications and quality standards. You will use precision measurement "
            "tools, maintain inspection records, and work cross-functionally to identify root "
            "causes of non-conformances and drive corrective action."
        ),
        "responsibilities": [
            "Perform incoming, in-process, and final inspections using calipers, gauges, CMM, and visual inspection",
            "Compare measurements and attributes to engineering drawings, specifications, and control plans",
            "Document inspection results in quality management systems and maintain traceability records",
            "Write Non-Conformance Reports (NCRs) and facilitate disposition of rejected material",
            "Support root cause analysis and corrective/preventive action (CAPA) processes",
            "Participate in supplier audits, customer audits, and internal quality audits",
            "Assist with calibration of measuring equipment per established schedules",
        ],
        "requirements": [
            "High school diploma; associate's degree or technical certificate in Quality, Manufacturing, or related field preferred",
            "2+ years of quality inspection or quality control experience in a manufacturing environment",
            "Proficiency with precision measurement tools (calipers, micrometers, height gauges, CMM)",
            "Familiarity with ISO 9001 quality management system requirements",
            "Detail-oriented with strong documentation skills",
        ],
        "preferred": [
            "ASQ Certified Quality Inspector (CQI) or Certified Quality Technician (CQT)",
            "Experience with GD&T (Geometric Dimensioning and Tolerancing)",
            "Knowledge of SPC (Statistical Process Control) methods",
        ],
    },

    # ── Corporate & Professional ───────────────────────────────────────────────

    "hr-generalist": {
        "summary": (
            "The HR Generalist is a versatile HR professional who supports employees and managers "
            "across the full employment lifecycle. You will handle employee relations, benefits "
            "administration, onboarding, compliance, and HRIS maintenance — serving as a trusted "
            "advisor and operational resource for the business."
        ),
        "responsibilities": [
            "Manage the onboarding and offboarding process for all employees",
            "Administer employee benefits programs and serve as the primary employee contact for enrollment and claims issues",
            "Maintain accurate employee records in the HRIS and ensure data integrity",
            "Support employee relations by investigating complaints, documenting findings, and recommending resolutions",
            "Ensure compliance with federal, state, and local employment laws including I-9, EEO, FMLA, and ADA",
            "Assist managers with performance management, coaching, and corrective action documentation",
            "Develop and maintain HR policies and employee handbook content",
        ],
        "requirements": [
            "Bachelor's degree in Human Resources, Business Administration, or related field",
            "3+ years of generalist HR experience",
            "Working knowledge of federal and state employment law",
            "Proficiency with HRIS platforms (Workday, BambooHR, ADP, or similar)",
            "Strong interpersonal skills and discretion in handling confidential information",
        ],
        "preferred": [
            "SHRM-CP or PHR certification",
            "Experience in a multi-state workforce environment",
            "Familiarity with Applicant Tracking Systems (ATS)",
        ],
    },

    "hr-business-partner": {
        "summary": (
            "The HR Business Partner (HRBP) serves as a strategic advisor to senior leaders and "
            "people managers, aligning HR initiatives with business objectives. You will lead "
            "talent planning, organizational effectiveness, change management, and complex employee "
            "relations — partnering deeply with assigned client groups to build high-performing teams."
        ),
        "responsibilities": [
            "Partner with senior leaders to develop and execute people strategies aligned with business goals",
            "Advise managers on organizational design, role clarity, and workforce planning",
            "Lead talent review and succession planning processes for assigned business units",
            "Manage complex employee relations matters including investigations and performance plans",
            "Drive change management initiatives including restructures, mergers, and culture programs",
            "Analyze HR data and metrics to identify trends and present actionable recommendations to leadership",
            "Collaborate with Centers of Excellence (Talent Acquisition, Total Rewards, L&D) to deliver integrated solutions",
        ],
        "requirements": [
            "Bachelor's degree in HR, Business, or related field; Master's degree a plus",
            "5+ years of HR experience with at least 2 years as an HRBP or senior HR generalist",
            "Deep knowledge of employment law, organizational development, and talent management",
            "Proven ability to influence senior leaders and navigate organizational complexity",
            "Strong analytical and data visualization skills",
        ],
        "preferred": [
            "SHRM-SCP or SPHR certification",
            "Experience supporting a business unit of 500+ employees",
            "Coaching certification or executive coaching experience",
        ],
    },

    "recruiter": {
        "summary": (
            "The Recruiter manages full-cycle talent acquisition for assigned roles and business "
            "units. You will source candidates through diverse channels, conduct structured "
            "screening interviews, partner closely with hiring managers, and deliver an exceptional "
            "candidate experience from first touch through offer acceptance."
        ),
        "responsibilities": [
            "Partner with hiring managers to define role requirements, ideal candidate profiles, and sourcing strategies",
            "Post positions, source candidates via LinkedIn, job boards, referrals, and community channels",
            "Screen resumes and conduct phone or video screens to assess qualifications and cultural fit",
            "Manage candidates through the ATS, maintain pipeline hygiene, and provide consistent status updates",
            "Coordinate and facilitate structured interview processes with clear evaluation criteria",
            "Extend verbal and written offers; negotiate and close candidates effectively",
            "Track and report key recruiting metrics (time-to-fill, source-of-hire, offer acceptance rate)",
        ],
        "requirements": [
            "Bachelor's degree or equivalent experience",
            "3+ years of in-house or agency recruiting experience",
            "Proficiency with ATS platforms (Greenhouse, Lever, iCIMS, or similar)",
            "Strong sourcing skills including Boolean search and LinkedIn Recruiter",
            "Excellent communication skills and a candidate-first mindset",
        ],
        "preferred": [
            "PHR, SHRM-CP, or LinkedIn Recruiter certification",
            "Experience recruiting for technical or specialized roles",
            "Familiarity with structured interviewing and competency-based assessment frameworks",
        ],
    },

    "office-manager": {
        "summary": (
            "The Office Manager ensures the office runs smoothly by managing facilities, vendors, "
            "supplies, and administrative operations. You will serve as the go-to resource for "
            "building logistics, support executive assistants and administrative staff, and "
            "maintain a productive, well-organized workplace."
        ),
        "responsibilities": [
            "Oversee daily office operations including facilities management, vendor relationships, and supply procurement",
            "Manage office lease, utilities, parking, and building security access",
            "Coordinate IT support and asset management in partnership with the IT team",
            "Maintain office budget, track expenses, and process invoices and expense reports",
            "Organize company events, all-hands meetings, catering, and employee engagement activities",
            "Support accounts payable and basic bookkeeping functions as needed",
            "Onboard new employees with office orientation, equipment provisioning, and access setup",
        ],
        "requirements": [
            "3+ years of office management or senior administrative experience",
            "Strong organizational, prioritization, and multitasking skills",
            "Proficiency with Microsoft 365 or Google Workspace",
            "Excellent vendor negotiation and relationship-management skills",
            "Discretion in handling confidential company and personnel information",
        ],
        "preferred": [
            "Associate's or Bachelor's degree in Business Administration",
            "Experience managing an office of 50+ employees",
            "Basic accounting knowledge (QuickBooks, NetSuite, or equivalent)",
        ],
    },

    "executive-assistant": {
        "summary": (
            "The Executive Assistant provides high-level administrative support to one or more "
            "C-suite or senior executives. You will manage complex calendars, coordinate domestic "
            "and international travel, prepare board materials, and handle sensitive projects — "
            "acting as a trusted extension of the executive you support."
        ),
        "responsibilities": [
            "Manage complex and frequently changing executive calendars across multiple time zones",
            "Coordinate domestic and international travel including flights, hotels, ground transport, and itineraries",
            "Prepare and distribute board presentations, briefing documents, and meeting materials",
            "Screen and respond to correspondence on the executive's behalf as directed",
            "Process expense reports and reconcile corporate card statements on schedule",
            "Organize off-sites, leadership meetings, and team events end-to-end",
            "Handle confidential information with the highest level of discretion",
        ],
        "requirements": [
            "5+ years of executive assistant or chief-of-staff experience supporting C-level leaders",
            "Expert proficiency with calendar tools, Microsoft 365, and Google Workspace",
            "Exceptional written and verbal communication skills",
            "Ability to anticipate needs, act proactively, and manage competing priorities",
            "Proven discretion with sensitive and confidential information",
        ],
        "preferred": [
            "Experience supporting a CEO, CFO, or board-level committee",
            "Notary public certification",
            "Project management certification (PMP, CAPM, or equivalent)",
        ],
    },

    "accountant": {
        "summary": (
            "The Accountant maintains the accuracy and integrity of financial records through the "
            "full accounting cycle. You will manage general ledger entries, support the month-end "
            "and year-end close, perform reconciliations, and provide clean, timely financial "
            "data to support management decision-making and audit readiness."
        ),
        "responsibilities": [
            "Record journal entries and maintain the general ledger for assigned accounts",
            "Perform month-end close activities including accruals, prepayments, and intercompany reconciliations",
            "Reconcile balance-sheet accounts and investigate variances",
            "Assist in preparation of financial statements, management reports, and board packages",
            "Support internal and external audit processes by providing documentation and analysis",
            "Maintain fixed-asset schedules and depreciation calculations",
            "Ensure compliance with GAAP and company accounting policies",
        ],
        "requirements": [
            "Bachelor's degree in Accounting, Finance, or related field",
            "3+ years of accounting experience in a corporate or public accounting environment",
            "Proficiency with ERP accounting systems (SAP, NetSuite, QuickBooks, or similar)",
            "Strong Excel skills including pivot tables and VLOOKUP/XLOOKUP",
            "Knowledge of GAAP and solid analytical skills",
        ],
        "preferred": [
            "CPA license or active CPA candidate",
            "Public accounting (Big 4 or regional firm) experience",
            "Experience with consolidations, multi-currency accounting, or ASC 606 revenue recognition",
        ],
    },

    "bookkeeper": {
        "summary": (
            "The Bookkeeper maintains accurate day-to-day financial records for the organization. "
            "You will process accounts payable and receivable, reconcile bank and credit card "
            "statements, support payroll, and provide clean books that enable leadership to make "
            "informed business decisions."
        ),
        "responsibilities": [
            "Record daily financial transactions including sales, purchases, payments, and receipts",
            "Process vendor invoices and manage accounts payable payment run",
            "Invoice customers and follow up on outstanding receivables",
            "Reconcile bank, credit card, and petty cash accounts monthly",
            "Assist with payroll processing and tax payment remittances",
            "Prepare monthly financial reports and balance-sheet summaries for management",
            "Maintain organized, audit-ready financial documentation",
        ],
        "requirements": [
            "High school diploma; Associate's degree in Accounting or Business preferred",
            "3+ years of bookkeeping experience",
            "QuickBooks Online or Desktop proficiency (certification a plus)",
            "Attention to accuracy and strong organizational skills",
            "Discretion in handling confidential financial data",
        ],
        "preferred": [
            "QuickBooks ProAdvisor or similar certification",
            "Experience with Xero, FreshBooks, or Zoho Books",
            "Basic understanding of accrual accounting and payroll tax rules",
        ],
    },

    "payroll-specialist": {
        "summary": (
            "The Payroll Specialist ensures employees across all states are paid accurately and "
            "on time, every pay period. You will manage the end-to-end payroll cycle, handle tax "
            "filings, process garnishments, and maintain rigorous records in compliance with "
            "federal, state, and local payroll regulations."
        ),
        "responsibilities": [
            "Process multi-state payroll for salaried, hourly, and variable-pay employees on scheduled pay dates",
            "Review timekeeping data for accuracy and resolve discrepancies before processing",
            "Calculate and withhold federal, state, and local income taxes, Social Security, and Medicare",
            "Process wage garnishments, child support orders, and tax levies per legal requirements",
            "Remit payroll tax deposits on schedule and file quarterly/annual returns (941, 940, W-2, etc.)",
            "Respond to employee payroll inquiries and resolve discrepancies promptly",
            "Maintain payroll audit trails and support internal and external audit requests",
        ],
        "requirements": [
            "3+ years of full-cycle multi-state payroll processing experience",
            "Proficiency with payroll software (ADP, Paylocity, Paycom, or similar)",
            "Knowledge of federal and state wage, hour, and payroll tax regulations",
            "High degree of accuracy and confidentiality",
            "Strong analytical and problem-solving skills",
        ],
        "preferred": [
            "Certified Payroll Professional (CPP) or FPC designation",
            "Experience processing payroll for 500+ employees",
            "Familiarity with HRIS integration and automated payroll feeds",
        ],
    },

    "paralegal": {
        "summary": (
            "The Paralegal supports attorneys by conducting legal research, drafting documents, "
            "managing cases, and handling e-filings. You will own significant administrative and "
            "substantive workflow under attorney supervision, directly improving throughput and "
            "service quality for the practice or legal department."
        ),
        "responsibilities": [
            "Conduct legal research using Westlaw, LexisNexis, and public databases",
            "Draft pleadings, motions, contracts, correspondence, and other legal documents for attorney review",
            "Manage case files, deadlines, and dockets including court calendaring systems",
            "Prepare for depositions, hearings, and trials by organizing exhibits and witness materials",
            "Coordinate e-filing of documents with state and federal courts using required platforms",
            "Liaise with clients, courts, opposing counsel, and expert witnesses",
            "Summarize depositions, discovery documents, and medical records",
        ],
        "requirements": [
            "Paralegal certificate from an ABA-approved program or Bachelor's degree in Paralegal Studies or related field",
            "2+ years of paralegal experience in a law firm or corporate legal department",
            "Proficiency with legal research databases (Westlaw, LexisNexis) and case management software",
            "Excellent writing, organizational, and deadline-management skills",
            "Understanding of court procedures and rules in applicable jurisdiction",
        ],
        "preferred": [
            "NALA Certified Paralegal (CP) or NFPA CORE Registered Paralegal (RP) designation",
            "Specialization in litigation, corporate law, real estate, or employment law",
            "Experience with e-discovery platforms (Relativity, Everlaw)",
        ],
    },

    # ── Tech & Engineering ─────────────────────────────────────────────────────

    "software-engineer": {
        "summary": (
            "The Software Engineer designs, builds, and ships features on a modern web or mobile "
            "stack. You will write clean, tested code, participate in code reviews, collaborate "
            "with product and design, and share in on-call responsibilities — taking real ownership "
            "of the systems you build."
        ),
        "responsibilities": [
            "Design and implement features across the full stack (frontend and/or backend depending on team)",
            "Write comprehensive unit, integration, and end-to-end tests",
            "Participate in code reviews and hold yourself and teammates to high engineering standards",
            "Collaborate with Product and Design to define requirements and shape technical approach",
            "Monitor production systems, respond to incidents, and perform root cause analysis",
            "Document architecture decisions and maintain up-to-date technical documentation",
            "Contribute to engineering-wide initiatives including tooling, reliability, and developer experience",
        ],
        "requirements": [
            "Bachelor's degree in Computer Science, Engineering, or equivalent practical experience",
            "2+ years of professional software development experience",
            "Proficiency in at least one modern programming language (Python, TypeScript/JavaScript, Go, Java, etc.)",
            "Familiarity with cloud platforms (AWS, GCP, or Azure) and containerization (Docker, Kubernetes)",
            "Strong problem-solving skills and intellectual curiosity",
        ],
        "preferred": [
            "Experience with the specific stack used by the team",
            "Open-source contributions or side projects demonstrating technical depth",
            "Familiarity with distributed systems, event-driven architecture, or data engineering",
        ],
    },

    "senior-software-engineer": {
        "summary": (
            "The Senior Software Engineer drives technical excellence on the team — setting the "
            "design bar, mentoring engineers, and leading delivery of complex, high-impact systems. "
            "You will be equally comfortable writing production code and influencing the technical "
            "roadmap, and you will help define what great looks like for the engineering org."
        ),
        "responsibilities": [
            "Lead the design and implementation of complex, cross-functional features and platform improvements",
            "Produce technical design documents and drive architectural decision records (ADRs)",
            "Mentor junior and mid-level engineers through code reviews, pairing, and design critiques",
            "Partner with Product and Engineering leadership to scope and estimate roadmap initiatives",
            "Establish and uphold engineering standards for quality, reliability, and security",
            "Investigate and resolve complex production incidents and systemic reliability issues",
            "Represent engineering perspective in cross-functional planning and prioritization",
        ],
        "requirements": [
            "5+ years of software engineering experience with a track record of shipping impactful systems",
            "Deep proficiency in at least one language and demonstrated polyglot capability",
            "Experience designing and operating distributed systems at scale",
            "Strong mentorship and technical communication skills",
            "Demonstrated ownership of production systems through the full lifecycle",
        ],
        "preferred": [
            "Staff or tech-lead experience with cross-team influence",
            "Domain expertise relevant to the team (e.g., payments, identity, data pipelines)",
            "Published engineering blog posts or conference talks",
        ],
    },

    "product-manager": {
        "summary": (
            "The Product Manager owns the product roadmap for one or more product areas. "
            "You will discover problems worth solving, define requirements in close partnership "
            "with engineering and design, and drive go-to-market execution — ensuring the team "
            "ships products that delight users and move business metrics."
        ),
        "responsibilities": [
            "Develop and maintain a prioritized product roadmap grounded in user research and business strategy",
            "Write detailed product requirements documents (PRDs) and user stories with clear acceptance criteria",
            "Conduct user interviews, usability studies, and competitive analysis to continuously improve product intuition",
            "Partner with Engineering and Design in sprint planning, grooming, and retrospectives",
            "Define and track success metrics; analyze usage data to make informed product decisions",
            "Drive go-to-market planning in partnership with Marketing, Sales, and Customer Success",
            "Communicate roadmap and progress to stakeholders and leadership",
        ],
        "requirements": [
            "3+ years of product management experience in a B2B or B2C software environment",
            "Proven ability to translate ambiguous problems into clear product requirements",
            "Strong analytical skills and comfort with product analytics tools (Amplitude, Mixpanel, Looker)",
            "Excellent written and verbal communication skills",
            "Demonstrated experience shipping product from zero to one",
        ],
        "preferred": [
            "MBA or relevant advanced degree",
            "Technical background or experience working on API/platform products",
            "Experience with growth or monetization product areas",
        ],
    },

    "designer": {
        "summary": (
            "The Product Designer shapes the end-to-end experience of our product — from user "
            "research and concept validation through pixel-perfect UI. You will own design "
            "across one or more product surfaces, contribute to the design system, and "
            "collaborate closely with Product and Engineering to ship work that is both "
            "beautiful and functional."
        ),
        "responsibilities": [
            "Lead UX research including user interviews, usability testing, and synthesis",
            "Create wireframes, interaction flows, prototypes, and high-fidelity UI designs",
            "Contribute to and maintain the design system, ensuring consistency across the product",
            "Collaborate with Product Managers to define problems and evaluate solutions",
            "Work closely with engineers during implementation to preserve design intent",
            "Conduct design critiques and mentor junior designers on craft and process",
            "Stay current with accessibility standards (WCAG 2.1) and apply them throughout",
        ],
        "requirements": [
            "3+ years of product design experience at a software company",
            "Expert proficiency with Figma and design system tooling",
            "Strong portfolio demonstrating end-to-end product thinking and visual craft",
            "Experience conducting and synthesizing UX research",
            "Ability to communicate design rationale to cross-functional stakeholders",
        ],
        "preferred": [
            "Experience designing complex data-heavy or enterprise products",
            "Familiarity with front-end development (CSS, React basics) for better engineering partnership",
            "Motion design skills",
        ],
    },

    "devops-engineer": {
        "summary": (
            "The DevOps / Site Reliability Engineer builds and maintains the infrastructure, "
            "tooling, and processes that keep production reliable and enable engineering teams "
            "to ship fast and confidently. You will own CI/CD pipelines, cloud infrastructure, "
            "observability, and incident response for critical systems."
        ),
        "responsibilities": [
            "Design, build, and maintain cloud infrastructure using infrastructure-as-code (Terraform, Pulumi, CDK)",
            "Own and improve CI/CD pipelines for fast, safe, and automated deployments",
            "Build and maintain observability stack including logging, metrics, alerting, and distributed tracing",
            "Participate in on-call rotation and lead incident response and post-mortems",
            "Harden production environments for security, compliance, and reliability",
            "Collaborate with engineering teams to establish SLOs and drive reliability improvements",
            "Evaluate and adopt new tools and practices that improve developer experience and system performance",
        ],
        "requirements": [
            "3+ years of DevOps, Platform Engineering, or SRE experience",
            "Proficiency with cloud platforms (AWS, GCP, or Azure) and containerization (Kubernetes, Docker)",
            "Experience with infrastructure-as-code tools and GitOps practices",
            "Strong scripting ability in Python, Bash, or Go",
            "Deep understanding of networking, security, and distributed systems fundamentals",
        ],
        "preferred": [
            "AWS/GCP/Azure Professional-level certification",
            "Experience with service mesh (Istio, Linkerd) or eBPF-based observability",
            "Background in a high-traffic, SLA-critical production environment",
        ],
    },

    "data-analyst": {
        "summary": (
            "The Data Analyst transforms raw data into actionable insights that guide product, "
            "marketing, and business decisions. You will own analytical projects end to end — "
            "from data extraction and modeling through dashboarding and stakeholder communication — "
            "and act as a trusted data resource for your assigned business areas."
        ),
        "responsibilities": [
            "Write efficient SQL queries to extract, transform, and analyze data from the data warehouse",
            "Build and maintain self-service dashboards and reports in BI tools (Looker, Tableau, Metabase)",
            "Design and analyze A/B tests including experimental design, sample sizing, and results interpretation",
            "Proactively identify trends, anomalies, and opportunities through exploratory data analysis",
            "Partner with Product, Marketing, and Operations stakeholders to frame business questions and deliver insights",
            "Document data models, metric definitions, and analytical methodologies",
            "Contribute to data quality monitoring and pipeline reliability",
        ],
        "requirements": [
            "2+ years of data analyst or business intelligence experience",
            "Advanced SQL proficiency across multiple dialects (PostgreSQL, BigQuery, Snowflake, or similar)",
            "Experience with at least one BI tool (Looker, Tableau, Power BI, Metabase)",
            "Strong analytical reasoning and ability to communicate findings to non-technical audiences",
            "Solid understanding of statistical concepts relevant to A/B testing",
        ],
        "preferred": [
            "Proficiency in Python or R for advanced analysis",
            "dbt experience for data modeling and transformation",
            "Background in product analytics, growth, or marketing analytics",
        ],
    },

    "it-support-specialist": {
        "summary": (
            "The IT Support Specialist provides Tier 1 and Tier 2 technical support to employees, "
            "ensuring fast, effective resolution of hardware, software, and connectivity issues. "
            "You will manage device provisioning, SaaS access, identity lifecycle, and endpoint "
            "management to keep the organization running securely and productively."
        ),
        "responsibilities": [
            "Serve as first point of contact for IT support requests via ticketing system, chat, and walk-up",
            "Diagnose and resolve hardware, software, network, and peripheral issues for Mac, Windows, and mobile devices",
            "Provision and deploy laptops, phones, and other endpoints using MDM (Jamf, Intune, or similar)",
            "Manage user accounts, groups, and permissions across identity platforms (Okta, Azure AD, Google Workspace)",
            "Onboard new employees by provisioning equipment, access, and conducting IT orientation",
            "Maintain IT asset inventory, hardware lifecycle tracking, and license management",
            "Escalate complex issues to Tier 3 or managed service provider and track to resolution",
        ],
        "requirements": [
            "2+ years of IT support or helpdesk experience",
            "Proficiency supporting macOS and Windows environments",
            "Experience with MDM platforms (Jamf, Intune, or equivalent) and SSO/identity tools (Okta, Azure AD)",
            "Strong troubleshooting methodology and documentation habits",
            "Customer-service mindset with clear, patient communication skills",
        ],
        "preferred": [
            "CompTIA A+, Network+, or Security+ certification",
            "Experience in a SaaS-heavy, cloud-first company environment",
            "Basic scripting ability (Bash, PowerShell) for automation",
        ],
    },

    # ── Sales & Marketing ─────────────────────────────────────────────────────

    "account-executive": {
        "summary": (
            "The Account Executive owns the full sales cycle for a defined territory or segment — "
            "from pipeline generation and discovery through negotiation and close. You will carry "
            "a quota, build multi-threaded champion relationships, and partner with Sales "
            "Engineering, Marketing, and Customer Success to win and expand strategic accounts."
        ),
        "responsibilities": [
            "Develop and execute a territory plan to build a pipeline at or above quota coverage targets",
            "Run a structured sales process: discovery, demo, business-case development, negotiation, close",
            "Qualify opportunities rigorously using MEDDIC, SPICED, or equivalent framework",
            "Build multi-threaded relationships across economic buyers, champions, and technical evaluators",
            "Forecast accurately in CRM (Salesforce, HubSpot) and maintain rigorous pipeline hygiene",
            "Partner with Solutions Engineering on POCs and technical evaluation processes",
            "Collaborate with Customer Success on expansion and renewal strategy for key accounts",
        ],
        "requirements": [
            "3+ years of full-cycle B2B SaaS or enterprise software sales experience",
            "Demonstrated track record of meeting or exceeding quota",
            "Proficiency with sales CRM (Salesforce or HubSpot) and outbound tooling (Outreach, Apollo)",
            "Strong business-case development and ROI storytelling skills",
            "Excellent discovery, negotiation, and executive communication skills",
        ],
        "preferred": [
            "Experience selling to HR, Finance, or Operations buyers",
            "MEDDIC/MEDDICC or SPICED sales methodology certification or training",
            "Startup AE experience including self-serve pipeline generation",
        ],
    },

    "sdr": {
        "summary": (
            "The Sales Development Representative (SDR) generates qualified pipeline for the "
            "Account Executive team through outbound prospecting and inbound lead qualification. "
            "You will research target accounts, execute multi-touch sequences, and connect "
            "prospects to the right AE — building the discipline and craft to advance into a "
            "closing role."
        ),
        "responsibilities": [
            "Research target accounts and build prospect lists using ZoomInfo, LinkedIn Sales Navigator, or equivalent",
            "Execute outbound prospecting sequences via email, phone, and LinkedIn",
            "Qualify inbound marketing leads and convert them to sales-accepted opportunities",
            "Conduct discovery calls to identify pain, urgency, and budget fit",
            "Hand off qualified opportunities to Account Executives with full context and documentation",
            "Maintain accurate activity and pipeline records in the CRM",
            "Collaborate with Marketing on messaging iteration and campaign feedback",
        ],
        "requirements": [
            "1+ year of SDR, BDR, or inside sales experience (internships or recent graduates considered)",
            "Strong written communication and cold-outreach skills",
            "Proficiency with sales engagement platforms (Outreach, Salesloft, Apollo, or equivalent)",
            "High activity level, coachability, and resilience",
            "Goal-oriented with a track record of hitting daily/weekly KPIs",
        ],
        "preferred": [
            "Experience prospecting into HR, Operations, or Finance buyers",
            "Salesforce or HubSpot CRM proficiency",
            "Bachelor's degree in Business, Communications, or related field",
        ],
    },

    "customer-success-manager": {
        "summary": (
            "The Customer Success Manager owns the post-sale relationship for a portfolio of "
            "accounts, driving adoption, retention, and expansion. You will partner with customers "
            "to ensure they achieve their desired outcomes, conduct regular business reviews, and "
            "identify growth opportunities — serving as the voice of the customer internally."
        ),
        "responsibilities": [
            "Own the success of a book of business including onboarding, adoption, renewal, and expansion",
            "Conduct regular Executive Business Reviews (EBRs) and health-check calls",
            "Build and maintain relationships with stakeholders at multiple levels within customer accounts",
            "Monitor product usage data and proactively engage at-risk customers",
            "Identify, qualify, and facilitate expansion and upsell opportunities with the AE team",
            "Serve as the escalation point for customer issues and drive resolution cross-functionally",
            "Capture product feedback and represent the customer perspective to Product and Engineering",
        ],
        "requirements": [
            "3+ years of customer success, account management, or client services experience in SaaS",
            "Demonstrated retention and expansion track record",
            "Strong executive-communication and relationship-building skills",
            "Proficiency with CS platforms (Gainsight, ChurnZero, or Totango) and CRM",
            "Analytical ability to use product data and health metrics to drive outcomes",
        ],
        "preferred": [
            "Experience managing enterprise accounts ($100K+ ARR)",
            "Domain expertise in HR Tech, Fintech, or vertical SaaS",
            "Salesforce or HubSpot CRM advanced proficiency",
        ],
    },

    "marketing-manager": {
        "summary": (
            "The Marketing Manager plans and executes integrated marketing programs across demand "
            "generation, content, and brand. You will manage channels, own the content calendar, "
            "partner with Sales to support pipeline goals, and ensure consistent, high-quality "
            "brand expression across all customer touchpoints."
        ),
        "responsibilities": [
            "Develop and execute integrated marketing campaigns across email, paid, social, and organic channels",
            "Own and manage the content calendar; coordinate content production with internal and external contributors",
            "Track, analyze, and report on campaign performance, optimizing for pipeline and MQL targets",
            "Partner with Sales to align on ICP, messaging, and campaign-to-close feedback",
            "Manage relationships with agencies, freelancers, and marketing technology vendors",
            "Maintain brand standards across all marketing materials and digital properties",
            "Manage the marketing budget and ensure programs deliver measurable ROI",
        ],
        "requirements": [
            "4+ years of B2B or B2C marketing experience",
            "Proven success running multi-channel demand-generation campaigns",
            "Proficiency with marketing automation (HubSpot, Marketo, or Pardot) and CRM",
            "Strong analytical skills and experience with marketing attribution",
            "Excellent written communication and brand sensibility",
        ],
        "preferred": [
            "Experience marketing to SMB or mid-market audiences",
            "Hands-on paid media management (Google Ads, LinkedIn Ads)",
            "Google Analytics 4 certification or equivalent",
        ],
    },

    "content-marketer": {
        "summary": (
            "The Content Marketer creates and distributes content that attracts, educates, and "
            "converts the target audience. You will own blog, email, SEO, and social content — "
            "developing a consistent editorial voice while building organic traffic and nurturing "
            "prospects through the funnel."
        ),
        "responsibilities": [
            "Research and write long-form blog posts, guides, and thought leadership content optimized for SEO",
            "Develop email nurture sequences, newsletters, and campaign copy",
            "Plan and execute social media content across LinkedIn, Twitter/X, and other relevant channels",
            "Conduct keyword research and maintain an SEO content roadmap aligned with organic traffic goals",
            "Repurpose content across formats (blog → social → email → video scripts)",
            "Track content performance through Google Search Console, GA4, and HubSpot",
            "Collaborate with designers, subject-matter experts, and external contributors",
        ],
        "requirements": [
            "3+ years of content marketing experience with a strong writing portfolio",
            "Demonstrated SEO knowledge including keyword research, on-page optimization, and link building",
            "Experience with email marketing platforms (HubSpot, Mailchimp, Klaviyo, or similar)",
            "Strong editorial judgment and ability to adapt tone for different audiences",
            "Data-driven mindset with experience measuring content performance",
        ],
        "preferred": [
            "HubSpot Content Marketing or Google Analytics certification",
            "Experience with video scripts, podcasts, or webinar content",
            "Technical writing or domain expertise in HR, Legal, Finance, or SaaS",
        ],
    },

    "social-media-manager": {
        "summary": (
            "The Social Media Manager owns the company's presence across social platforms — "
            "developing strategy, creating content, managing the community, and measuring "
            "impact. You will build brand affinity, drive engagement, and support broader "
            "marketing and business development goals through authentic, platform-native content."
        ),
        "responsibilities": [
            "Develop and execute platform-specific social media strategies for LinkedIn, Instagram, X/Twitter, TikTok, and others",
            "Create, schedule, and publish organic content aligned with the editorial calendar",
            "Monitor, respond to, and engage with community comments, mentions, and DMs",
            "Manage paid social campaigns in coordination with the Demand Generation team",
            "Track and report on follower growth, reach, engagement, and conversion from social channels",
            "Stay current on platform algorithm changes, trends, and format innovations",
            "Collaborate with design, content, and PR teams to produce high-quality assets",
        ],
        "requirements": [
            "3+ years of social media management experience for a brand or agency",
            "Demonstrated ability to grow followers and engagement across multiple platforms",
            "Proficiency with social media management tools (Sprout Social, Buffer, Hootsuite, or similar)",
            "Basic graphic design skills (Canva, Adobe Express) for post creation",
            "Strong copywriting skills and native platform sensibility",
        ],
        "preferred": [
            "Experience with paid social advertising (Meta Ads, LinkedIn Campaign Manager)",
            "Video production and short-form video editing skills (CapCut, Premiere Rush)",
            "Influencer or creator partnership experience",
        ],
    },
}
