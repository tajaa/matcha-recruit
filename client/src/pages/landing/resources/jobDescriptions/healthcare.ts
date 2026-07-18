import type { JDContent } from './types'

export const healthcare: Record<string, JDContent> = {
  'registered-nurse': {
    summary: 'The Registered Nurse provides direct patient care in accordance with evidence-based practice, physician orders, and applicable nursing standards. You will assess patient conditions, administer medications, develop and monitor care plans, and collaborate with interdisciplinary teams to achieve optimal patient outcomes.',
    responsibilities: [
      'Perform comprehensive patient assessments and document findings in the EMR',
      'Administer medications and treatments per provider orders and the five rights of medication administration',
      'Develop, implement, and evaluate individualized nursing care plans',
      'Communicate patient status changes to physicians and care team members promptly',
      'Educate patients and families on conditions, medications, and discharge instructions',
      'Supervise and delegate tasks to LPN/LVN and CNA staff per scope of practice',
      'Maintain strict compliance with HIPAA, infection control, and Joint Commission standards',
    ],
    requirements: [
      'Active and unrestricted RN license in the applicable state',
      "Associate's degree in Nursing (ADN) or Bachelor of Science in Nursing (BSN)",
      'Current BLS certification; ACLS preferred for acute care settings',
      'Strong clinical assessment and critical-thinking skills',
      'Proficiency with electronic medical record (EMR) systems',
    ],
    preferred: [
      'BSN and 2+ years of clinical experience in the relevant specialty',
      'Specialty certification (CCRN, CEN, Med-Surg Certification, etc.)',
      'Experience with EPIC, Cerner, or equivalent EMR platform',
    ],
  },

  'lvn-lpn': {
    summary: 'The Licensed Vocational Nurse (LVN) / Licensed Practical Nurse (LPN) provides direct patient care under the supervision of a Registered Nurse or physician. You will collect vitals, administer medications, perform wound care, and document all interventions accurately in the EMR.',
    responsibilities: [
      'Collect and record patient vital signs and basic health information',
      'Administer oral, topical, and injectable medications per scope of practice and provider orders',
      'Perform wound assessment, dressing changes, and basic wound care procedures',
      'Assist with patient admissions, transfers, and discharges',
      'Communicate patient concerns and changes in condition to supervising RN or physician',
      'Maintain accurate and timely documentation in the EMR',
      'Follow infection control, safety, and HIPAA compliance protocols',
    ],
    requirements: [
      'Active and unrestricted LVN/LPN license in the applicable state',
      'Completion of an accredited LVN/LPN program',
      'Current BLS certification',
      'Ability to perform physical tasks including prolonged standing and lifting up to 50 lbs with assistance',
      'Strong attention to detail and documentation accuracy',
    ],
    preferred: [
      '1+ year of LVN/LPN experience in a clinical or long-term care setting',
      'IV certification (where applicable by state)',
      'Familiarity with EMR platforms (EPIC, PointClickCare, etc.)',
    ],
  },

  'medical-assistant': {
    summary: 'The Medical Assistant supports clinical and administrative operations in a physician office, clinic, or outpatient setting. You will room patients, document chief complaints in the EMR, perform phlebotomy and basic diagnostics, and assist providers with examinations — keeping the clinic running on time and at a high standard of care.',
    responsibilities: [
      'Room patients, obtain vital signs, and document reason for visit in the EMR prior to provider entry',
      'Assist providers during examinations and minor procedures',
      'Perform phlebotomy, EKGs, urinalysis, and other in-office diagnostic tests',
      'Prepare and administer medications and vaccinations per provider order and protocol',
      'Schedule follow-up appointments and coordinate referrals and prior authorizations',
      'Maintain exam-room supplies, equipment logs, and medication inventory',
      'Perform front-desk and clerical duties including patient check-in, phone triage, and insurance verification',
    ],
    requirements: [
      'Medical Assistant diploma or certificate from an accredited program',
      'CMA (AAMA), RMA (AMT), or equivalent certification (or eligibility within 12 months of hire)',
      'Current BLS/CPR certification',
      'Proficiency with EMR software; experience with athenahealth, EPIC, or eClinicalWorks a plus',
      'Ability to maintain patient confidentiality in accordance with HIPAA',
    ],
    preferred: [
      '1+ years of clinical medical assistant experience',
      'Bilingual skills to support diverse patient populations',
      'Experience with prior-authorization and insurance-verification workflows',
    ],
  },

  'cna': {
    summary: 'The Certified Nursing Assistant (CNA) provides direct personal care to patients or residents under the supervision of licensed nursing staff. You will assist with activities of daily living (ADLs), monitor and document vital signs, and maintain a safe and supportive environment for those in your care.',
    responsibilities: [
      'Assist patients/residents with bathing, dressing, grooming, oral hygiene, and toileting',
      'Collect and document vital signs including blood pressure, pulse, respiration, and temperature',
      'Reposition patients as directed to prevent pressure injuries',
      'Assist with ambulation, transfers, and mobility using proper body mechanics and equipment',
      'Report changes in patient condition, behavior, or skin integrity to supervising RN/LPN',
      'Follow infection control protocols and maintain a clean care environment',
      'Document all care provided accurately and in a timely manner',
    ],
    requirements: [
      'Active CNA certification in the applicable state',
      'Completion of a state-approved nursing assistant training program',
      'Current BLS/CPR certification',
      'Compassionate patient-care attitude and strong communication skills',
      'Ability to perform physically demanding tasks including lifting/transferring up to 50 lbs with assistance',
    ],
    preferred: [
      '6+ months of CNA experience in a hospital, SNF, or home health setting',
      'Experience with memory care or behavioral health populations',
      'Bilingual language skills',
    ],
  },

  'phlebotomist': {
    summary: 'The Phlebotomist collects blood and other specimens from patients for laboratory analysis. You will ensure proper patient identification, perform venipuncture and capillary collection with a high first-stick success rate, process and label specimens accurately, and maintain a calm, patient-centered environment.',
    responsibilities: [
      'Verify patient identity using two identifiers before every collection',
      'Perform venipuncture, capillary puncture, and other specimen collection techniques',
      'Label all specimens accurately at point of collection and process per laboratory protocol',
      'Package and transport specimens according to handling and temperature requirements',
      'Explain collection procedures to patients and manage patient anxiety effectively',
      'Maintain supply inventory, equipment logs, and collection station cleanliness',
      'Adhere to all infection control, safety, and HIPAA standards',
    ],
    requirements: [
      'Phlebotomy certification (CPT-ASCP, NPA, or state equivalent) or completion of accredited phlebotomy program',
      'Current BLS/CPR certification',
      'Demonstrated high first-stick success rate',
      'Attention to detail and accuracy in specimen labeling and documentation',
      'Ability to work calmly with patients of all ages including pediatric patients',
    ],
    preferred: [
      '1+ year of phlebotomy experience in a hospital, lab, or outpatient setting',
      'Experience with LIS (Laboratory Information System) software',
      'Bilingual skills',
    ],
  },

  'medical-receptionist': {
    summary: 'The Medical Receptionist is the face of the practice and manages all front-office functions to ensure a smooth patient flow. You will greet patients, schedule and confirm appointments, verify insurance, collect copays, and maintain HIPAA-compliant patient records.',
    responsibilities: [
      'Greet patients and visitors courteously upon arrival and departure',
      'Schedule, confirm, and cancel patient appointments using the practice management system',
      'Verify insurance eligibility and obtain prior authorizations as required',
      'Collect copays, deductibles, and outstanding balances; post payments accurately',
      'Maintain and update patient demographic and insurance information in the EMR',
      'Answer multi-line phone system, triage calls, and relay accurate messages to clinical staff',
      'Scan, file, and manage medical records in accordance with HIPAA privacy regulations',
    ],
    requirements: [
      'High school diploma or equivalent',
      '1+ year of medical front-office or customer-service experience',
      'Familiarity with insurance verification, CPT and ICD-10 codes, and billing basics',
      'Proficiency with EMR/practice management software (athenahealth, NextGen, or similar)',
      'Strong interpersonal skills and patient-first attitude',
    ],
    preferred: [
      'Medical office administration certificate or associate\'s degree',
      'Bilingual communication skills',
      'Experience with referral coordination and prior authorization workflows',
    ],
  },

  'behavioral-health-technician': {
    summary: 'The Behavioral Health Technician (BHT) provides direct support and supervision to patients in psychiatric, substance-use, or behavioral health treatment settings. You will monitor patient safety, facilitate therapeutic activities, document observations, and assist the clinical team in delivering trauma-informed care.',
    responsibilities: [
      'Conduct regular patient observations and document behavior, mood, and safety status',
      'Maintain a safe therapeutic milieu and intervene during behavioral escalations using approved de-escalation techniques',
      'Assist patients with daily living activities and group participation',
      'Transport patients to/from appointments, activities, and therapeutic groups as assigned',
      'Complete admissions intake documentation, inventory of personal property, and orientation',
      'Implement individualized behavior support plans under clinical supervision',
      'Communicate relevant patient observations to the nursing and clinical team',
    ],
    requirements: [
      "High school diploma or equivalent; Bachelor's degree in psychology or related field a plus",
      'Completion of BHT training or Mental Health Worker certification (state-specific requirements may apply)',
      'Current CPR/BLS certification; de-escalation or CPI training preferred',
      'Empathy, patience, and strong boundary-setting skills',
      'Ability to work in a high-acuity environment including nights and weekends',
    ],
    preferred: [
      '1+ year of experience in an inpatient psychiatric, residential, or substance-use treatment setting',
      'Knowledge of motivational interviewing or cognitive behavioral techniques',
      'Bilingual communication skills',
    ],
  },

  'home-health-aide': {
    summary: 'The Home Health Aide provides non-medical personal care and companionship to clients in their homes, supporting their independence and quality of life. You will assist with activities of daily living, light housekeeping, medication reminders, and basic vital-sign monitoring under the direction of a supervising nurse or care coordinator.',
    responsibilities: [
      'Assist clients with bathing, dressing, grooming, oral hygiene, and toileting',
      'Prepare nutritious meals and snacks according to dietary restrictions and care plans',
      'Perform light housekeeping, laundry, and household organization tasks',
      'Monitor and record vital signs (temperature, pulse, blood pressure) as directed',
      'Provide medication reminders and assist with self-administered medications per agency protocol',
      'Accompany clients to medical appointments and community activities',
      'Document care provided and report changes in client condition to the supervising nurse',
    ],
    requirements: [
      'Home Health Aide certificate or HHA competency test completion (state requirements apply)',
      'Current CPR/BLS certification',
      'Valid driver\'s license and reliable transportation',
      'Compassionate, patient, and dependable work style',
      'Ability to perform physical tasks including lifting and transferring clients with assistance',
    ],
    preferred: [
      '6+ months of HHA or personal care aide experience',
      "Experience supporting clients with dementia, Parkinson's, or post-surgical recovery",
      'Bilingual language skills',
    ],
  },
}
