"""Handbook static data — state names, mandatory-topic rules, guided-industry
playbook, operational-hook patterns (J6 split of handbook_service.py)."""
import re
from datetime import date, datetime, timedelta, timezone

__all__ = [
    "STATE_NAMES",
    "ADDENDUM_CORE_CATEGORIES",
    "ADDENDUM_FALLBACK_REVIEW_LINE",
    "ADDENDUM_KEYWORD_PATTERNS",
    "STRICT_TEMPLATE_INDUSTRIES",
    "MANDATORY_STATE_TOPIC_RULES",
    "MANDATORY_STATE_TOPIC_LABELS",
    "LEGAL_OPERATIONAL_HOOKS",
    "ATTENDANCE_NOTICE_WINDOW_HOOK",
    "WORKWEEK_DAY_ALIASES",
    "WORKWEEK_TIME_PATTERN",
    "WORKWEEK_TIMEZONE_PATTERN",
    "EMAIL_PATTERN",
    "GUIDED_PROFILE_BOOL_KEYS",
    "GUIDED_PROFILE_NUMERIC_KEYS",
    "GUIDED_COMMON_QUESTIONS",
    "GUIDED_INDUSTRY_PLAYBOOK",
    "GUIDED_INDUSTRY_ALIASES",
    "_NUMERIC_GENEROUS_CATEGORIES",
    "_LEVEL_PRIORITY",
]


STATE_NAMES = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "DC": "District of Columbia",
}
ADDENDUM_CORE_CATEGORIES = (
    "minimum_wage",
    "overtime",
    "sick_leave",
    "meal_breaks",
    "pay_frequency",
    "final_pay",
    "minor_work_permit",
    "scheduling_reporting",
)
ADDENDUM_FALLBACK_REVIEW_LINE = (
    "No verified statutory entries were found in the compliance repository for this topic. "
    "Run a compliance refresh and complete legal review before publishing."
)
ADDENDUM_KEYWORD_PATTERNS = (
    "%lactation%",
    "%pregnan%",
    "%disability benefit%",
    "%disability insurance%",
    "%family leave%",
    "%paid family%",
    "%reasonable accommodation%",
    "%anti-retaliation%",
    "%domestic violence%",
    "%final pay%",
    "%final paycheck%",
    "%separation pay%",
    "%minor work%",
    "%youth employment%",
    "%child labor%",
    "%predictive scheduling%",
    "%fair workweek%",
    "%reporting time%",
)
STRICT_TEMPLATE_INDUSTRIES = {"hospitality"}
MANDATORY_STATE_TOPIC_RULES: dict[str, tuple[str, ...]] = {
    "minimum_wage": ("minimum_wage", "minimum wage", "wage floor", "min wage", "hourly wage", "wage and hour"),
    "overtime": ("overtime", "time and a half", "overtime pay", "hours worked", "weekly hours"),
    "pay_frequency": ("pay_frequency", "pay frequency", "payday", "pay period", "wage payment", "pay schedule"),
    "sick_leave": ("sick_leave", "paid sick", "sick leave", "sick time", "pto", "paid time off", "earned sick"),
    "meal_breaks": ("meal_break", "meal period", "rest break", "meal and rest", "break period", "rest period", "meal break"),
    "final_pay": ("final_pay", "final pay", "final paycheck", "separation pay", "final wage", "last paycheck", "termination pay"),
    "minor_work_permit": ("minor_work_permit", "minor work", "youth employment", "child labor", "working minor"),
    "scheduling_reporting": ("scheduling_reporting", "predictive scheduling", "fair workweek", "reporting time", "work schedule", "shift scheduling"),
    "discrimination": ("discrimination", "equal employment", "protected class", "anti-discrimination", "title vii", "eeoc"),
    "workers_compensation": ("workers_compensation", "workers compensation", "workers' compensation", "workplace injury", "injury report", "work-related injury"),
    "family_leave": ("family_leave", "family leave", "fmla", "parental leave", "maternity leave", "paternity leave", "family medical"),
    "pregnancy_accommodation": ("pregnancy_accommodation", "pregnancy", "pregnant worker", "lactation", "nursing mother", "reasonable accommodation"),
    "harassment": ("harassment", "anti-harassment", "sexual harassment", "hostile work environment", "harassment policy", "harassment training"),
}
MANDATORY_STATE_TOPIC_LABELS: dict[str, str] = {
    "minimum_wage": "minimum wage",
    "overtime": "overtime",
    "pay_frequency": "pay frequency",
    "sick_leave": "paid sick leave",
    "meal_breaks": "meal/rest breaks",
    "final_pay": "final pay",
    "minor_work_permit": "youth employment",
    "scheduling_reporting": "scheduling/reporting time",
    "discrimination": "discrimination/EEO",
    "workers_compensation": "workers' compensation",
    "family_leave": "family/medical leave",
    "pregnancy_accommodation": "pregnancy accommodation",
    "harassment": "harassment prevention",
}
LEGAL_OPERATIONAL_HOOKS = {
    "hr_contact_email": "[HR_CONTACT_EMAIL]",
    "leave_admin_email": "[LEAVE_ADMIN_EMAIL]",
    "harassment_hotline": "[HARASSMENT_REPORTING_HOTLINE]",
    "harassment_email": "[HARASSMENT_REPORTING_EMAIL]",
    "workweek_start_day": "[WORKWEEK_START_DAY]",
    "workweek_start_time": "[WORKWEEK_START_TIME]",
    "workweek_timezone": "[WORKWEEK_TIMEZONE]",
    "payday_frequency": "[PAYDAY_FREQUENCY]",
    "payday_anchor": "[PAYDAY_ANCHOR_DAY]",
    "legal_owner": "[LEGAL_REVIEW_OWNER]",
}
ATTENDANCE_NOTICE_WINDOW_HOOK = "[ATTENDANCE_NOTICE_WINDOW]"
WORKWEEK_DAY_ALIASES = {
    "mon": "Monday",
    "monday": "Monday",
    "tue": "Tuesday",
    "tues": "Tuesday",
    "tuesday": "Tuesday",
    "wed": "Wednesday",
    "weds": "Wednesday",
    "wednesday": "Wednesday",
    "thu": "Thursday",
    "thur": "Thursday",
    "thurs": "Thursday",
    "thursday": "Thursday",
    "fri": "Friday",
    "friday": "Friday",
    "sat": "Saturday",
    "saturday": "Saturday",
    "sun": "Sunday",
    "sunday": "Sunday",
}
WORKWEEK_TIME_PATTERN = re.compile(
    r"\b((?:[01]?\d|2[0-3])(?::[0-5]\d)?\s?(?:AM|PM)?)\b",
    re.IGNORECASE,
)
WORKWEEK_TIMEZONE_PATTERN = re.compile(
    r"\b(PT|PST|PDT|MT|MST|MDT|CT|CST|CDT|ET|EST|EDT|UTC(?:[+-]\d{1,2})?|GMT(?:[+-]\d{1,2})?)\b",
    re.IGNORECASE,
)
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
GUIDED_PROFILE_BOOL_KEYS = {
    "remote_workers",
    "minors",
    "tipped_employees",
    "union_employees",
    "federal_contracts",
    "group_health_insurance",
    "background_checks",
    "hourly_employees",
    "salaried_employees",
    "commissioned_employees",
    "tip_pooling",
}
GUIDED_PROFILE_NUMERIC_KEYS = {"headcount"}
GUIDED_COMMON_QUESTIONS = [
    {
        "id": "hr_contact_email",
        "question": "What email should employees use for HR policy questions?",
        "placeholder": "hr@company.com",
        "required": True,
    },
    {
        "id": "leave_admin_email",
        "question": "What email should employees use for leave and accommodation requests?",
        "placeholder": "leave@company.com",
        "required": True,
    },
    {
        "id": "harassment_hotline",
        "question": "What hotline number or reporting channel should be listed for harassment complaints?",
        "placeholder": "24/7 hotline number or internal reporting channel",
        "required": True,
    },
    {
        "id": "harassment_email",
        "question": "What email should be listed as a harassment reporting channel?",
        "placeholder": "hr-reports@company.com",
        "required": True,
    },
    {
        "id": "workweek_definition",
        "question": "When does your payroll workweek start (day, time, and timezone)?",
        "placeholder": "Sunday 12:00 AM PT",
        "required": True,
    },
    {
        "id": "payday_frequency",
        "question": "What payroll cadence applies for regular paydays?",
        "placeholder": "e.g., weekly or biweekly",
        "required": True,
    },
    {
        "id": "payday_anchor",
        "question": "What day should be used as the payroll anchor/cutoff reference?",
        "placeholder": "e.g., Friday",
        "required": True,
    },
    {
        "id": "attendance_notice_window",
        "question": "What call-out notice window should apply for foreseeable absences?",
        "placeholder": "24 hours advance notice",
        "required": True,
    },
]
GUIDED_INDUSTRY_PLAYBOOK = {
    "general": {
        "label": "General Employer",
        "summary": "General employment baseline with enforceable reporting, wage/hour, leave, and anti-retaliation controls.",
        "profile_defaults": {
            "hourly_employees": True,
        },
        "questions": [
            {
                "id": "discipline_escalation_matrix",
                "question": "How should corrective action escalate (coaching, written warning, suspension, termination)?",
                "placeholder": "Define standard escalation path",
                "required": False,
            },
            {
                "id": "manager_training_frequency",
                "question": "How often should managers complete policy and anti-retaliation training?",
                "placeholder": "e.g., annually",
                "required": False,
            },
        ],
        "sections": [
            {
                "title": "Reporting and Escalation Protocol",
                "content": (
                    "Employees may report policy concerns to supervisors, Human Resources at [HR_CONTACT_EMAIL], "
                    "or through [HARASSMENT_REPORTING_HOTLINE]. Reports may be made without fear of retaliation. "
                    "All managers must escalate complaints to HR within one business day."
                ),
            },
            {
                "title": "Attendance and Absence Control Matrix",
                "content": (
                    "Foreseeable absences require at least [ATTENDANCE_NOTICE_WINDOW] notice unless a protected leave law applies. "
                    "Unforeseeable absences must be reported before shift start. "
                    "Excused and unexcused absences are evaluated under company policy and applicable sick leave law."
                ),
            },
        ],
    },
    "hospitality": {
        "label": "Hospitality / Restaurants",
        "summary": "Adds tipped-employee controls, service-shift scheduling, and tip-pool governance expectations.",
        "profile_defaults": {
            "hourly_employees": True,
            "tipped_employees": True,
            "tip_pooling": True,
        },
        "questions": [
            {
                "id": "tip_credit_policy",
                "question": "Do you use tip credit by location, and if so, where?",
                "placeholder": "State/local rules where tip credit is used",
                "required": True,
            },
            {
                "id": "tip_pool_roles",
                "question": "Which job roles are included/excluded from tip pooling?",
                "placeholder": "Servers, bartenders, bussers included; managers excluded",
                "required": True,
            },
            {
                "id": "service_cutoff_reporting",
                "question": "What same-day escalation process applies to guest incidents and workplace complaints?",
                "placeholder": "Who must be notified and within what timeframe",
                "required": False,
            },
        ],
        "sections": [
            {
                "title": "Tipped Employee and Tip Pool Compliance",
                "content": (
                    "Tip ownership remains with employees unless a lawful tip pool applies. "
                    "Managers and supervisors may not retain employee tips. "
                    "Tip pool eligibility and distribution must match state/local law and the approved role matrix."
                ),
            },
            {
                "title": "Shift Scheduling and Rest Period Controls",
                "content": (
                    "Scheduling managers must provide compliant meal/rest opportunities and avoid off-the-clock prep or close-out work. "
                    "Shift swaps require manager approval and documented coverage confirmation."
                ),
            },
        ],
    },
    "healthcare": {
        "label": "Healthcare",
        "summary": "Adds HIPAA privacy, credentialing, infection control, bloodborne pathogen, patient safety, and healthcare scheduling controls.",
        "profile_defaults": {
            "hourly_employees": True,
            "background_checks": True,
            "group_health_insurance": True,
        },
        "questions": [
            {
                "id": "credentialing_review_owner",
                "question": "Who owns credential/licensure verification and escalation for lapses?",
                "placeholder": "Department + role",
                "required": True,
            },
            {
                "id": "patient_safety_reporting_window",
                "question": "What is the required reporting window for patient safety or workplace safety incidents?",
                "placeholder": "e.g., immediate verbal report + written report within 24h",
                "required": True,
            },
            {
                "id": "hipaa_privacy_officer",
                "question": "Who serves as the HIPAA Privacy Officer (and Security Officer, if separate)?",
                "placeholder": "Name/title and contact",
                "required": True,
            },
            {
                "id": "infection_control_officer",
                "question": "Who is the designated Infection Control Officer or committee lead?",
                "placeholder": "Name/title or committee name",
                "required": True,
            },
            {
                "id": "shift_structure",
                "question": "What shift structures does your facility use?",
                "placeholder": "e.g., 8-hour, 10-hour, 12-hour, rotating",
                "required": False,
            },
            {
                "id": "overtime_exemption_8_80",
                "question": "Does your facility use the FLSA 8/80 overtime exemption for hospital employees?",
                "placeholder": "Yes / No / Not sure",
                "required": False,
            },
            {
                "id": "mandatory_reporting_categories",
                "question": "What categories require mandatory external reporting (e.g., CMS events, state-reportable conditions, abuse/neglect)?",
                "placeholder": "List applicable categories",
                "required": False,
            },
        ],
        "sections": [
            {
                "title": "Credentialing and Scope-of-Practice Compliance",
                "content": (
                    "Employees must perform duties within their active licensure and scope-of-practice limits. "
                    "Managers must verify active credentials before assignment changes and escalate lapses immediately. "
                    "The organization maintains a credentialing verification process that includes primary source "
                    "verification of all required licenses, certifications, and registrations at hire and upon renewal."
                ),
            },
            {
                "title": "Patient Safety and Non-Retaliation Reporting",
                "content": (
                    "Employees must report patient safety and workplace safety concerns immediately through established channels. "
                    "Good-faith safety reporting is protected from retaliation. Sentinel events, near-misses, and adverse "
                    "outcomes must be documented per the facility's incident reporting procedures."
                ),
            },
            {
                "title": "HIPAA Privacy and Security Obligations",
                "content": (
                    "All employees must protect Protected Health Information (PHI) in accordance with the HIPAA Privacy Rule "
                    "and Security Rule. Access to patient records is limited to the minimum necessary for job duties. "
                    "Employees must complete HIPAA training at hire and annually thereafter. Any suspected breach or "
                    "unauthorized disclosure must be reported to the Privacy Officer immediately."
                ),
            },
            {
                "title": "Bloodborne Pathogen Exposure Control",
                "content": (
                    "The facility maintains an Exposure Control Plan in compliance with OSHA's Bloodborne Pathogens "
                    "Standard (29 CFR 1910.1030). Employees must follow Universal Precautions, use appropriate PPE, "
                    "and report all needlestick injuries, sharps injuries, and mucous membrane exposures immediately. "
                    "Post-exposure evaluation, prophylaxis, and follow-up are provided at no cost to the employee."
                ),
            },
            {
                "title": "Infection Prevention and Control",
                "content": (
                    "All employees must adhere to the facility's infection prevention protocols, including hand hygiene, "
                    "standard and transmission-based precautions, and proper use of personal protective equipment (PPE). "
                    "Employees with communicable illnesses must notify their supervisor before reporting to work."
                ),
            },
            {
                "title": "Mandatory Overtime Restrictions and Shift Scheduling",
                "content": (
                    "Scheduling practices comply with applicable state mandatory overtime restrictions for healthcare workers. "
                    "Employees are not required to work beyond their scheduled shift except in declared emergencies as "
                    "defined by applicable law. Minimum rest periods between shifts are observed per state requirements."
                ),
            },
            {
                "title": "Professional Licensure and Continuing Education",
                "content": (
                    "Licensed and certified employees are responsible for maintaining active, unrestricted credentials "
                    "and meeting all continuing education requirements mandated by their licensing boards. Employees "
                    "must provide proof of renewal to Human Resources before expiration. Failure to maintain required "
                    "credentials may result in reassignment or separation."
                ),
            },
            {
                "title": "Workplace Violence Prevention (Healthcare)",
                "content": (
                    "The facility maintains a workplace violence prevention program specific to healthcare settings. "
                    "Employees must report threats, aggressive behavior, or violent incidents immediately. "
                    "De-escalation training is provided to patient-facing staff. The facility conducts periodic "
                    "risk assessments of clinical areas in compliance with applicable state healthcare workplace violence laws."
                ),
            },
        ],
    },
    "retail": {
        "label": "Retail",
        "summary": "Adds shift scheduling, timekeeping integrity, and customer-floor conduct controls for retail operations.",
        "profile_defaults": {
            "hourly_employees": True,
        },
        "questions": [
            {
                "id": "opening_closing_checklist",
                "question": "What opening/closing checklist controls should be mandatory for timekeeping and safety?",
                "placeholder": "Clock-in/out, cash count, alarm check, safety walkthrough",
                "required": False,
            },
            {
                "id": "loss_prevention_escalation",
                "question": "How should suspected theft, violence, or safety incidents be escalated?",
                "placeholder": "Escalation owner and response timeline",
                "required": False,
            },
        ],
        "sections": [
            {
                "title": "Store Shift Compliance Controls",
                "content": (
                    "Opening and closing activities must be completed on the clock. "
                    "Managers must verify break compliance, time edits, and end-of-shift handoff records each day."
                ),
            },
            {
                "title": "Customer-Facing Conduct and Incident Escalation",
                "content": (
                    "Employees must de-escalate customer conflicts and immediately report threats, violence, or discriminatory behavior. "
                    "Serious incidents must be escalated to leadership and HR without delay."
                ),
            },
        ],
    },
    "manufacturing": {
        "label": "Manufacturing / Warehouse",
        "summary": "Adds safety-critical controls, shift handoff requirements, and incident escalation for operational sites.",
        "profile_defaults": {
            "hourly_employees": True,
        },
        "questions": [
            {
                "id": "safety_shutdown_authority",
                "question": "Who can stop production for safety and how is restart approval handled?",
                "placeholder": "Role/title + restart authority",
                "required": True,
            },
            {
                "id": "ppe_enforcement_protocol",
                "question": "What PPE enforcement and corrective action protocol should apply?",
                "placeholder": "Required PPE and escalation sequence",
                "required": True,
            },
        ],
        "sections": [
            {
                "title": "Safety-Critical Work and Stop-Work Authority",
                "content": (
                    "Any employee may stop work when an imminent safety hazard exists. "
                    "Operations may resume only after hazard review and documented management authorization."
                ),
            },
            {
                "title": "Shift Handoff, Lockout/Tagout, and Incident Reporting",
                "content": (
                    "Shift transitions must include documented equipment status, outstanding hazards, and lockout/tagout controls where applicable. "
                    "Injuries, near misses, and safety concerns must be reported immediately."
                ),
            },
        ],
    },
    "technology": {
        "label": "Technology / Professional Services",
        "summary": "Adds remote-work governance, data security expectations, and responsive investigation channels.",
        "profile_defaults": {
            "remote_workers": True,
            "salaried_employees": True,
        },
        "questions": [
            {
                "id": "remote_work_jurisdiction_tracking",
                "question": "How should employees report work-location changes for tax and compliance tracking?",
                "placeholder": "Notice window + approval workflow",
                "required": True,
            },
            {
                "id": "security_incident_reporting_window",
                "question": "What is the response window for suspected data/privacy incidents?",
                "placeholder": "e.g., immediate to security@company.com",
                "required": True,
            },
        ],
        "sections": [
            {
                "title": "Remote Work Location and Payroll Compliance",
                "content": (
                    "Employees must obtain approval before changing primary work location across state lines. "
                    "Location changes must be reported promptly to maintain wage/hour, tax, and leave-law compliance."
                ),
            },
            {
                "title": "Data Security, Privacy, and Investigations",
                "content": (
                    "Employees must protect confidential and personal data under company security policies. "
                    "Suspected privacy or security incidents must be reported immediately through approved channels."
                ),
            },
        ],
    },
}
GUIDED_INDUSTRY_ALIASES = {
    "restaurant": "hospitality",
    "hospitality": "hospitality",
    "food": "hospitality",
    "hotel": "hospitality",
    "health": "healthcare",
    "medical": "healthcare",
    "clinic": "healthcare",
    "retail": "retail",
    "store": "retail",
    "shop": "retail",
    "warehouse": "manufacturing",
    "manufacturing": "manufacturing",
    "industrial": "manufacturing",
    "technology": "technology",
    "software": "technology",
    "saas": "technology",
    "professional services": "technology",
    "consulting": "technology",
}
# Categories where higher numeric_value = more employee-friendly
_NUMERIC_GENEROUS_CATEGORIES = {"minimum_wage"}
# Jurisdiction level priority: more local = generally more generous
_LEVEL_PRIORITY = {"city": 3, "county": 2, "state": 1}
