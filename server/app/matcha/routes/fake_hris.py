"""
Fake HRIS router that simulates an ADP Workforce Now API.

Serves 55 behavioral health specialist employees with realistic
credential data. Mounted at /api/fake-hris.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(tags=["fake-hris"])


# ---------------------------------------------------------------------------
# Auth models
# ---------------------------------------------------------------------------

class TokenRequest(BaseModel):
    client_id: str
    client_secret: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int


# ---------------------------------------------------------------------------
# Bearer validation dependency
# ---------------------------------------------------------------------------

def _require_bearer(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Bearer token")


# ---------------------------------------------------------------------------
# Raw employee seed data
# ---------------------------------------------------------------------------
# Each tuple: (first, last, role, specialty, license_type, license_number,
#               npi, dea, board_cert, board_cert_exp, malpractice_carrier,
#               malpractice_policy, malpractice_exp, hire_date,
#               worker_type, is_manager, department, phone_last4,
#               clinical_specialty, license_exp, dea_exp,
#               extra_string_fields, extra_date_fields)

_RAW_EMPLOYEES: list[dict] = []


def _md(first: str, last: str, role: str, **kw) -> dict:
    """Shorthand to build a raw employee dict."""
    d = {"first": first, "last": last, "role": role}
    d.update(kw)
    return d


_npi_counter = 1234567890


def _next_npi() -> str:
    global _npi_counter
    val = str(_npi_counter)
    _npi_counter += 1
    return val


# --- Psychiatrists (7) ---
_RAW_EMPLOYEES += [
    _md("Sarah", "Chen", "Psychiatrist",
        specialty="Addiction Psychiatry", license_type="MD",
        license_number="A123456", npi=_next_npi(), dea="FC1234563",
        board_cert="ABPN - Addiction Psychiatry",
        board_cert_exp="2028-12-31", malpractice_carrier="NORCAL Group",
        malpractice_policy="MP-2026-001", malpractice_exp="2027-01-01",
        hire_date="2023-06-15", license_exp="2027-06-30", dea_exp="2027-12-31",
        department="Adult Psychiatry", phone_last4="0101"),
    _md("David", "Okafor", "Psychiatrist",
        specialty="Child & Adolescent Psychiatry", license_type="MD",
        license_number="A128734", npi=_next_npi(), dea="FO2345671",
        board_cert="ABPN - Child & Adolescent Psychiatry",
        board_cert_exp="2029-03-31", malpractice_carrier="The Doctors Company",
        malpractice_policy="MP-2026-002", malpractice_exp="2027-03-15",
        hire_date="2022-09-01", license_exp="2027-09-30", dea_exp="2028-06-30",
        department="Child & Adolescent Services", phone_last4="0102",
        is_manager=True),
    _md("Maria", "Gutierrez-Reyes", "Psychiatrist",
        specialty="Forensic Psychiatry", license_type="DO",
        license_number="A134290", npi=_next_npi(), dea="FG3456782",
        board_cert="ABPN - Forensic Psychiatry",
        board_cert_exp="2028-06-30", malpractice_carrier="ProAssurance",
        malpractice_policy="MP-2026-003", malpractice_exp="2027-06-01",
        hire_date="2021-11-15", license_exp="2027-11-30", dea_exp="2028-05-31",
        department="Forensic Services", phone_last4="0103"),
    _md("James", "Whitfield", "Psychiatrist",
        specialty="Consultation-Liaison Psychiatry", license_type="MD",
        license_number="A141057", npi=_next_npi(), dea="FW4567893",
        board_cert="ABPN - Consultation-Liaison Psychiatry",
        board_cert_exp="2029-01-31", malpractice_carrier="NORCAL Group",
        malpractice_policy="MP-2026-004", malpractice_exp="2027-01-01",
        hire_date="2023-01-10", license_exp="2028-01-31", dea_exp="2028-12-31",
        department="Consultation-Liaison", phone_last4="0104"),
    _md("Priya", "Ramanathan", "Psychiatrist",
        specialty="Geriatric Psychiatry", license_type="MD",
        license_number="A149823", npi=_next_npi(), dea="FR5678904",
        board_cert="ABPN - Geriatric Psychiatry",
        board_cert_exp="2028-09-30", malpractice_carrier="Coverys",
        malpractice_policy="MP-2026-005", malpractice_exp="2027-09-01",
        hire_date="2022-03-20", license_exp="2027-03-31", dea_exp="2028-03-31",
        department="Geriatric Psychiatry", phone_last4="0105"),
    _md("Marcus", "Jefferson", "Psychiatrist",
        specialty="General Adult Psychiatry", license_type="MD",
        license_number="A155691", npi=_next_npi(), dea="FJ6789015",
        board_cert="ABPN - General Psychiatry",
        board_cert_exp="2029-06-30", malpractice_carrier="The Doctors Company",
        malpractice_policy="MP-2026-006", malpractice_exp="2027-06-01",
        hire_date="2024-01-08", license_exp="2028-06-30", dea_exp="2029-06-30",
        department="Adult Psychiatry", phone_last4="0106"),
    _md("Yuki", "Tanaka", "Psychiatrist",
        specialty="Addiction Psychiatry", license_type="MD",
        license_number="A162478", npi=_next_npi(), dea="FT7890126",
        board_cert="ABPN - Addiction Psychiatry",
        board_cert_exp="2029-12-31", malpractice_carrier="NORCAL Group",
        malpractice_policy="MP-2026-007", malpractice_exp="2027-12-01",
        hire_date="2023-08-15", license_exp="2028-08-31", dea_exp="2029-08-31",
        department="Substance Use Disorders", phone_last4="0107"),
]

# --- Psychologists (6) ---
_RAW_EMPLOYEES += [
    _md("Rachel", "Abramowitz", "Psychologist",
        specialty="Clinical Psychology", license_type="PsyD",
        license_number="PSY31245", npi=_next_npi(),
        board_cert="ABPP - Clinical Psychology",
        board_cert_exp="2029-05-31",
        hire_date="2022-07-01", license_exp="2027-07-31",
        department="Psychology", phone_last4="0108"),
    _md("Carlos", "Mendoza", "Psychologist",
        specialty="Neuropsychology", license_type="PhD",
        license_number="PSY31890", npi=_next_npi(),
        board_cert="ABPP - Clinical Neuropsychology",
        board_cert_exp="2028-11-30",
        hire_date="2021-05-15", license_exp="2027-05-31",
        department="Neuropsychology", phone_last4="0109"),
    _md("Amara", "Osei", "Psychologist",
        specialty="Forensic Psychology", license_type="PhD",
        license_number="PSY32456", npi=_next_npi(),
        board_cert="ABPP - Forensic Psychology",
        board_cert_exp="2029-02-28",
        hire_date="2023-02-01", license_exp="2028-02-28",
        department="Forensic Services", phone_last4="0110"),
    _md("Daniel", "Kowalski", "Psychologist",
        specialty="Health Psychology", license_type="PsyD",
        license_number="PSY33012", npi=_next_npi(),
        hire_date="2024-03-01", license_exp="2028-03-31",
        department="Integrated Health", phone_last4="0111"),
    _md("Fatima", "Al-Rashid", "Psychologist",
        specialty="Clinical Psychology", license_type="PsyD",
        license_number="PSY33578", npi=_next_npi(),
        hire_date="2023-10-15", license_exp="2028-10-31",
        department="Psychology", phone_last4="0112"),
    _md("Kevin", "Park", "Psychologist",
        specialty="Clinical Psychology", license_type="PhD",
        license_number="PSY34101", npi=_next_npi(),
        board_cert="ABPP - Clinical Psychology",
        board_cert_exp="2029-08-31",
        hire_date="2022-01-10", license_exp="2027-01-31",
        department="Psychology", phone_last4="0113",
        is_manager=True),
]

# --- Psychiatric Nurse Practitioners (5) ---
_RAW_EMPLOYEES += [
    _md("Angela", "Washington", "Psychiatric Nurse Practitioner",
        specialty="Adult PMHNP", license_type="PMHNP",
        license_number="NP95-12345", npi=_next_npi(), dea="AW8901237",
        board_cert="ANCC PMHNP-BC",
        board_cert_exp="2028-04-30", malpractice_carrier="NSO",
        malpractice_policy="MP-2026-008", malpractice_exp="2027-04-01",
        hire_date="2023-04-01", license_exp="2027-04-30", dea_exp="2028-04-30",
        department="Outpatient Psychiatry", phone_last4="0114",
        extra_string_fields=[
            {"nameCode": {"codeValue": "rn_license"}, "stringValue": "RN-734521"},
            {"nameCode": {"codeValue": "furnishing_number"}, "stringValue": "FN-12345"},
        ]),
    _md("Roberto", "Villarreal", "Psychiatric Nurse Practitioner",
        specialty="Child & Adolescent PMHNP", license_type="PMHNP",
        license_number="NP95-12890", npi=_next_npi(), dea="RV9012348",
        board_cert="ANCC PMHNP-BC",
        board_cert_exp="2029-01-31", malpractice_carrier="CM&F Group",
        malpractice_policy="MP-2026-009", malpractice_exp="2027-01-15",
        hire_date="2022-11-01", license_exp="2027-11-30", dea_exp="2028-11-30",
        department="Child & Adolescent Services", phone_last4="0115",
        extra_string_fields=[
            {"nameCode": {"codeValue": "rn_license"}, "stringValue": "RN-745892"},
            {"nameCode": {"codeValue": "furnishing_number"}, "stringValue": "FN-12890"},
        ]),
    _md("Thanh", "Nguyen", "Psychiatric Nurse Practitioner",
        specialty="Geriatric PMHNP", license_type="PMHNP",
        license_number="NP95-13456", npi=_next_npi(), dea="TN0123459",
        board_cert="ANCC PMHNP-BC",
        board_cert_exp="2028-07-31", malpractice_carrier="NSO",
        malpractice_policy="MP-2026-010", malpractice_exp="2027-07-01",
        hire_date="2024-02-15", license_exp="2028-02-28", dea_exp="2029-02-28",
        department="Geriatric Psychiatry", phone_last4="0116",
        extra_string_fields=[
            {"nameCode": {"codeValue": "rn_license"}, "stringValue": "RN-758123"},
            {"nameCode": {"codeValue": "furnishing_number"}, "stringValue": "FN-13456"},
        ]),
    _md("Brittany", "Scott", "Psychiatric Nurse Practitioner",
        specialty="Substance Use PMHNP", license_type="PMHNP",
        license_number="NP95-14012", npi=_next_npi(), dea="BS1234560",
        board_cert="ANCC PMHNP-BC",
        board_cert_exp="2029-10-31", malpractice_carrier="Nurses Service Organization",
        malpractice_policy="MP-2026-011", malpractice_exp="2027-10-01",
        hire_date="2023-07-01", license_exp="2028-07-31", dea_exp="2029-07-31",
        department="Substance Use Disorders", phone_last4="0117",
        extra_string_fields=[
            {"nameCode": {"codeValue": "rn_license"}, "stringValue": "RN-769345"},
            {"nameCode": {"codeValue": "furnishing_number"}, "stringValue": "FN-14012"},
        ]),
    _md("Oluwaseun", "Adeyemi", "Psychiatric Nurse Practitioner",
        specialty="Adult PMHNP", license_type="PMHNP",
        license_number="NP95-14578", npi=_next_npi(), dea="OA2345671",
        board_cert="ANCC PMHNP-BC",
        board_cert_exp="2028-12-31", malpractice_carrier="CM&F Group",
        malpractice_policy="MP-2026-012", malpractice_exp="2027-12-01",
        hire_date="2024-06-01", license_exp="2029-06-30", dea_exp="2029-12-31",
        department="Outpatient Psychiatry", phone_last4="0118",
        extra_string_fields=[
            {"nameCode": {"codeValue": "rn_license"}, "stringValue": "RN-780567"},
            {"nameCode": {"codeValue": "furnishing_number"}, "stringValue": "FN-14578"},
        ]),
]

# --- Licensed Clinical Social Workers (7) ---
_RAW_EMPLOYEES += [
    _md("Jessica", "Morales", "Licensed Clinical Social Worker",
        specialty="Trauma & PTSD", license_type="LCSW",
        license_number="LCS-28901", npi=_next_npi(),
        hire_date="2021-08-15", license_exp="2027-08-31",
        department="Clinical Social Work", phone_last4="0119"),
    _md("Terrence", "Brooks", "Licensed Clinical Social Worker",
        specialty="Substance Abuse", license_type="LCSW",
        license_number="LCS-29345", npi=_next_npi(),
        hire_date="2022-04-01", license_exp="2027-04-30",
        department="Substance Use Disorders", phone_last4="0120"),
    _md("Mei-Ling", "Wu", "Licensed Clinical Social Worker",
        specialty="Child & Family", license_type="LCSW",
        license_number="LCS-29789", npi=_next_npi(),
        hire_date="2023-01-15", license_exp="2028-01-31",
        department="Child & Adolescent Services", phone_last4="0121"),
    _md("Aisha", "Hassan", "Licensed Clinical Social Worker",
        specialty="Medical Social Work", license_type="LCSW",
        license_number="LCS-30234", npi=_next_npi(),
        hire_date="2022-10-01", license_exp="2027-10-31",
        department="Integrated Health", phone_last4="0122"),
    _md("Patrick", "O'Brien", "Licensed Clinical Social Worker",
        specialty="Crisis Intervention", license_type="LCSW",
        license_number="LCS-30678", npi=_next_npi(),
        hire_date="2024-05-01", license_exp="2029-05-31",
        department="Crisis Services", phone_last4="0123"),
    _md("Sonia", "Petrov", "Licensed Clinical Social Worker",
        specialty="Geriatric Social Work", license_type="LCSW",
        license_number="LCS-31122", npi=_next_npi(),
        hire_date="2023-09-15", license_exp="2028-09-30",
        department="Geriatric Psychiatry", phone_last4="0124"),
    _md("Andre", "Williams", "Licensed Clinical Social Worker",
        specialty="Group Therapy", license_type="LCSW",
        license_number="LCS-31567", npi=_next_npi(),
        hire_date="2021-12-01", license_exp="2027-12-31",
        department="Clinical Social Work", phone_last4="0125",
        is_manager=True),
]

# --- Licensed Marriage & Family Therapists (5) ---
_RAW_EMPLOYEES += [
    _md("Christina", "Flores", "Licensed Marriage & Family Therapist",
        specialty="Couples Therapy", license_type="LMFT",
        license_number="LMFT-45123", npi=_next_npi(),
        hire_date="2023-03-01", license_exp="2028-03-31",
        department="Family Therapy", phone_last4="0126"),
    _md("Brian", "Kim", "Licensed Marriage & Family Therapist",
        specialty="Adolescent & Family", license_type="LMFT",
        license_number="LMFT-45567", npi=_next_npi(),
        hire_date="2022-06-15", license_exp="2027-06-30",
        department="Child & Adolescent Services", phone_last4="0127"),
    _md("Natasha", "Volkov", "Licensed Marriage & Family Therapist",
        specialty="Trauma-Informed Family Therapy", license_type="LMFT",
        license_number="LMFT-46012", npi=_next_npi(),
        hire_date="2024-01-15", license_exp="2029-01-31",
        department="Family Therapy", phone_last4="0128"),
    _md("Darnell", "Robinson", "Licensed Marriage & Family Therapist",
        specialty="Multicultural Family Systems", license_type="LMFT",
        license_number="LMFT-46456", npi=_next_npi(),
        hire_date="2023-05-01", license_exp="2028-05-31",
        department="Family Therapy", phone_last4="0129"),
    _md("Elena", "Stavros", "Licensed Marriage & Family Therapist",
        specialty="Emotionally Focused Therapy", license_type="LMFT",
        license_number="LMFT-46901", npi=_next_npi(),
        hire_date="2022-08-01", license_exp="2027-08-31",
        department="Family Therapy", phone_last4="0130"),
]

# --- Licensed Professional Counselors (4) ---
_RAW_EMPLOYEES += [
    _md("Jamal", "Carter", "Licensed Professional Clinical Counselor",
        specialty="Cognitive Behavioral Therapy", license_type="LPCC",
        license_number="LPCC-10234", npi=_next_npi(),
        hire_date="2023-11-01", license_exp="2028-11-30",
        department="Counseling", phone_last4="0131"),
    _md("Samantha", "Lee", "Licensed Professional Clinical Counselor",
        specialty="Dialectical Behavior Therapy", license_type="LPCC",
        license_number="LPCC-10678", npi=_next_npi(),
        hire_date="2024-04-15", license_exp="2029-04-30",
        department="Counseling", phone_last4="0132"),
    _md("Miguel", "Santos", "Licensed Professional Clinical Counselor",
        specialty="EMDR Therapy", license_type="LPCC",
        license_number="LPCC-11123", npi=_next_npi(),
        hire_date="2022-12-01", license_exp="2027-12-31",
        department="Counseling", phone_last4="0133"),
    _md("Grace", "Nakamura", "Licensed Professional Clinical Counselor",
        specialty="Motivational Interviewing", license_type="LPCC",
        license_number="LPCC-11567", npi=_next_npi(),
        hire_date="2023-06-15", license_exp="2028-06-30",
        department="Counseling", phone_last4="0134"),
]

# --- Certified Alcohol & Drug Counselors (4) ---
_RAW_EMPLOYEES += [
    _md("Raymond", "Dixon", "Certified Alcohol & Drug Counselor",
        specialty="Substance Use Disorders", license_type="CADC-II",
        license_number="CADC-7890", npi=_next_npi(),
        hire_date="2022-05-01", license_exp="2027-05-31",
        department="Substance Use Disorders", phone_last4="0135"),
    _md("Luz", "Hernandez", "Certified Alcohol & Drug Counselor",
        specialty="Co-Occurring Disorders", license_type="CADC-II",
        license_number="CADC-8234",
        hire_date="2023-08-01", license_exp="2028-08-31",
        department="Substance Use Disorders", phone_last4="0136"),
    _md("Tyrone", "Mitchell", "Certified Alcohol & Drug Counselor",
        specialty="Opioid Use Disorder", license_type="CASAC",
        license_number="CASAC-5678", npi=_next_npi(),
        hire_date="2024-02-01", license_exp="2029-02-28",
        department="Substance Use Disorders", phone_last4="0137"),
    _md("Veronica", "Castillo", "Certified Alcohol & Drug Counselor",
        specialty="Adolescent Substance Abuse", license_type="CADC-II",
        license_number="CADC-8901",
        hire_date="2023-04-15", license_exp="2028-04-30",
        department="Substance Use Disorders", phone_last4="0138"),
]

# --- Board Certified Behavior Analysts (4) ---
_RAW_EMPLOYEES += [
    _md("Lauren", "Fischer", "Board Certified Behavior Analyst",
        specialty="Applied Behavior Analysis", license_type="BCBA",
        license_number="BACB-1-23-45678", npi=_next_npi(),
        board_cert="BACB - BCBA", board_cert_exp="2028-01-31",
        hire_date="2023-02-15", license_exp="2028-02-28",
        department="Behavioral Health", phone_last4="0139"),
    _md("Omar", "Shaikh", "Board Certified Behavior Analyst",
        specialty="Autism Spectrum Disorders", license_type="BCBA",
        license_number="BACB-1-23-56789", npi=_next_npi(),
        board_cert="BACB - BCBA", board_cert_exp="2028-06-30",
        hire_date="2022-09-15", license_exp="2027-09-30",
        department="Behavioral Health", phone_last4="0140"),
    _md("Stephanie", "Russo", "Board Certified Behavior Analyst",
        specialty="Pediatric Behavioral Health", license_type="BCBA",
        license_number="BACB-1-24-12345",
        board_cert="BACB - BCBA", board_cert_exp="2029-03-31",
        hire_date="2024-03-01", license_exp="2029-03-31",
        department="Child & Adolescent Services", phone_last4="0141"),
    _md("DeShawn", "Taylor", "Board Certified Behavior Analyst",
        specialty="Behavioral Interventions", license_type="BCBA",
        license_number="BACB-1-24-23456", npi=_next_npi(),
        board_cert="BACB - BCBA", board_cert_exp="2029-06-30",
        hire_date="2024-07-01", license_exp="2029-07-31",
        department="Behavioral Health", phone_last4="0142"),
]

# --- Psychiatric Registered Nurses (3) ---
_RAW_EMPLOYEES += [
    _md("Keisha", "Johnson", "Psychiatric Registered Nurse",
        specialty="Inpatient Psychiatric Nursing", license_type="RN",
        license_number="RN-812345", npi=_next_npi(),
        hire_date="2021-10-01", license_exp="2027-10-31",
        department="Inpatient Unit", phone_last4="0143"),
    _md("Thomas", "Murphy", "Psychiatric Registered Nurse",
        specialty="Crisis Stabilization Nursing", license_type="RN",
        license_number="RN-823456",
        hire_date="2023-03-15", license_exp="2028-03-31",
        department="Crisis Services", phone_last4="0144"),
    _md("Maria Elena", "Cruz", "Psychiatric Registered Nurse",
        specialty="Medication Administration", license_type="RN",
        license_number="RN-834567", npi=_next_npi(),
        hire_date="2022-07-15", license_exp="2027-07-31",
        department="Outpatient Psychiatry", phone_last4="0145"),
]

# --- Occupational Therapists (3) ---
_RAW_EMPLOYEES += [
    _md("Jennifer", "Chang", "Occupational Therapist",
        specialty="Mental Health OT", license_type="OTR",
        license_number="OT-56789", npi=_next_npi(),
        hire_date="2023-05-15", license_exp="2028-05-31",
        department="Rehabilitation", phone_last4="0146"),
    _md("Eric", "Johansson", "Occupational Therapist",
        specialty="Vocational Rehabilitation", license_type="OTR",
        license_number="OT-57234", npi=_next_npi(),
        hire_date="2024-01-01", license_exp="2029-01-31",
        department="Rehabilitation", phone_last4="0147"),
    _md("Nadira", "Patel", "Occupational Therapist",
        specialty="Sensory Integration", license_type="OTR",
        license_number="OT-57678", npi=_next_npi(),
        hire_date="2022-11-15", license_exp="2027-11-30",
        department="Rehabilitation", phone_last4="0148"),
]

# --- Art/Music Therapists (2) ---
_RAW_EMPLOYEES += [
    _md("Isabelle", "Moreau", "Art Therapist",
        specialty="Expressive Arts Therapy", license_type="ATR-BC",
        license_number="ATR-23456",
        hire_date="2023-09-01", license_exp="2028-09-30",
        department="Creative Arts Therapy", phone_last4="0149"),
    _md("Julian", "Rivera", "Music Therapist",
        specialty="Music Therapy", license_type="MT-BC",
        license_number="MT-34567",
        hire_date="2024-04-01", license_exp="2029-04-30",
        department="Creative Arts Therapy", phone_last4="0150"),
]

# --- Peer Support Specialists (3) ---
_RAW_EMPLOYEES += [
    _md("Dwayne", "Harris", "Peer Support Specialist",
        specialty="Peer Recovery Support", license_type="CPSS",
        license_number="CPSS-2024-1234",
        hire_date="2024-01-15", license_exp="2026-01-31",
        department="Peer Services", phone_last4="0151"),
    _md("Tamika", "Brown", "Peer Support Specialist",
        specialty="Family Peer Support", license_type="CPSS",
        license_number="CPSS-2023-5678",
        hire_date="2023-06-01", license_exp="2025-06-30",
        department="Peer Services", phone_last4="0152"),
    _md("Victor", "Dominguez", "Peer Support Specialist",
        specialty="Veterans Peer Support", license_type="CPSS",
        license_number="CPSS-2023-9012",
        hire_date="2023-10-01", license_exp="2025-10-31",
        department="Peer Services", phone_last4="0153"),
]

# --- Administrative Staff (2) ---
_RAW_EMPLOYEES += [
    _md("Linda", "Thompson", "Office Manager",
        hire_date="2020-03-01",
        department="Administration", phone_last4="0154"),
    _md("Ryan", "Gallagher", "Billing Coordinator",
        hire_date="2022-02-15",
        department="Administration", phone_last4="0155"),
]


# ---------------------------------------------------------------------------
# Build ADP-formatted worker objects
# ---------------------------------------------------------------------------

def _build_worker(idx: int, raw: dict) -> dict:
    """Convert a raw employee dict into ADP Workforce Now worker format."""
    aoid = f"WH-{idx + 1:03d}"
    first = raw["first"]
    last = raw["last"]
    clean_first = first.lower().replace(" ", "").replace("'", "").replace("-", "")
    clean_last = last.lower().replace(" ", "").replace("'", "")
    email = f"{clean_first}.{clean_last}@worldhealth.org"
    phone = f"310-555-{raw.get('phone_last4', f'{idx:04d}')}"

    # Custom fields
    string_fields: list[dict] = []
    date_fields: list[dict] = []

    license_type = raw.get("license_type")
    if license_type:
        string_fields.append(
            {"nameCode": {"codeValue": "license_type"}, "stringValue": license_type}
        )

    license_number = raw.get("license_number")
    if license_number:
        string_fields.append(
            {"nameCode": {"codeValue": "license_number"}, "stringValue": license_number}
        )

    npi = raw.get("npi")
    if npi:
        string_fields.append(
            {"nameCode": {"codeValue": "npi_number"}, "stringValue": npi}
        )

    dea = raw.get("dea")
    if dea:
        string_fields.append(
            {"nameCode": {"codeValue": "dea_number"}, "stringValue": dea}
        )

    board_cert = raw.get("board_cert")
    if board_cert:
        string_fields.append(
            {"nameCode": {"codeValue": "board_certification"}, "stringValue": board_cert}
        )

    malpractice_carrier = raw.get("malpractice_carrier")
    if malpractice_carrier:
        string_fields.append(
            {"nameCode": {"codeValue": "malpractice_carrier"}, "stringValue": malpractice_carrier}
        )

    malpractice_policy = raw.get("malpractice_policy")
    if malpractice_policy:
        string_fields.append(
            {"nameCode": {"codeValue": "malpractice_policy_number"}, "stringValue": malpractice_policy}
        )

    specialty = raw.get("specialty")
    if specialty:
        string_fields.append(
            {"nameCode": {"codeValue": "clinical_specialty"}, "stringValue": specialty}
        )

    # Append any extra string fields (e.g., RN license, furnishing number for PMHNPs)
    for extra in raw.get("extra_string_fields", []):
        string_fields.append(extra)

    license_exp = raw.get("license_exp")
    if license_exp:
        date_fields.append(
            {"nameCode": {"codeValue": "license_expiration"}, "dateValue": license_exp}
        )

    dea_exp = raw.get("dea_exp")
    if dea_exp:
        date_fields.append(
            {"nameCode": {"codeValue": "dea_expiration"}, "dateValue": dea_exp}
        )

    board_cert_exp = raw.get("board_cert_exp")
    if board_cert_exp:
        date_fields.append(
            {"nameCode": {"codeValue": "board_cert_expiration"}, "dateValue": board_cert_exp}
        )

    malpractice_exp = raw.get("malpractice_exp")
    if malpractice_exp:
        date_fields.append(
            {"nameCode": {"codeValue": "malpractice_expiration"}, "dateValue": malpractice_exp}
        )

    # Append any extra date fields
    for extra in raw.get("extra_date_fields", []):
        date_fields.append(extra)

    worker: dict = {
        "associateOID": aoid,
        "workerStatus": {"statusCode": {"codeValue": "Active"}},
        "person": {
            "legalName": {"givenName": first, "familyName1": last},
            "communication": {
                "emails": [{"emailUri": email}],
                "mobiles": [{"dialNumber": phone}],
            },
        },
        "workAssignments": [
            {
                "positionTitle": raw["role"],
                "managementPosition": raw.get("is_manager", False),
                "homeOrganizationalUnits": [
                    {
                        "nameCode": {"codeValue": raw.get("department", "Behavioral Health")},
                        "typeCode": {"codeValue": "Department"},
                    }
                ],
                "hireDate": raw.get("hire_date", "2024-01-01"),
                "workerTypeCode": {"codeValue": "Full-time"},
                "homeWorkLocation": {
                    "address": {
                        "countrySubdivisionLevel1": {"codeValue": "CA"},
                        "cityName": "Los Angeles",
                    }
                },
            }
        ],
    }

    if string_fields or date_fields:
        custom: dict = {}
        if string_fields:
            custom["stringFields"] = string_fields
        if date_fields:
            custom["dateFields"] = date_fields
        worker["customFieldGroup"] = custom

    return worker


FAKE_WORKERS: list[dict] = [
    _build_worker(i, emp) for i, emp in enumerate(_RAW_EMPLOYEES)
]

# Build a lookup by associateOID for O(1) single-worker retrieval
_WORKERS_BY_OID: dict[str, dict] = {w["associateOID"]: w for w in FAKE_WORKERS}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/auth/token", response_model=TokenResponse)
async def auth_token(body: TokenRequest):
    """Issue a mock ADP OAuth token."""
    return TokenResponse(
        access_token=f"mock-adp-token-{uuid.uuid4().hex[:16]}",
        token_type="Bearer",
        expires_in=3600,
    )


@router.get("/health")
async def health_check():
    """ADP health check endpoint."""
    return {"status": "ok", "provider": "adp_workforce_now", "version": "v2"}


@router.get("/hr/v2/workers", dependencies=[Depends(_require_bearer)])
async def list_workers(
    top: int = Query(20, alias="$top", ge=1, le=100),
    skip: int = Query(0, alias="$skip", ge=0),
):
    """Return paginated list of workers in ADP format."""
    page = FAKE_WORKERS[skip : skip + top]
    return {
        "workers": page,
        "meta": {
            "totalNumber": len(FAKE_WORKERS),
            "startIndex": skip,
            "itemsPerPage": top,
        },
    }


@router.get("/hr/v2/workers/{aoid}", dependencies=[Depends(_require_bearer)])
async def get_worker(aoid: str):
    """Return a single worker by associateOID."""
    worker = _WORKERS_BY_OID.get(aoid)
    if not worker:
        raise HTTPException(status_code=404, detail=f"Worker {aoid} not found")
    return {"workers": [worker]}
