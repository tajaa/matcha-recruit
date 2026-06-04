#!/usr/bin/env python3
"""Generate ADDITIVE demo WC data for broker 'Regina George LLC'
(ashVidales+regina@gmail.com). Purely additive — no DELETE, no DDL:

  - fills companies.industry ONLY where currently empty (so benchmarks resolve
    → severity bands + Premium Δ appear). Never overwrites an existing value.
  - INSERTs a small set of recordable incidents (tagged DEMO-REG-* so they are
    trivially reversible) to create milestones + a varied band spread on top of
    whatever data already exists.

Run:  python3 scripts/seed_regina_demo.py | ssh ... docker exec -i <pg> psql ...
Undo: DELETE FROM ir_incidents WHERE incident_number LIKE 'DEMO-REG-%';
"""

C = {
    "Bags":            "3e69de7a-0c0e-4a34-ab7b-3e9462756516",
    "Bowls":           "83abd6c1-461c-491c-9389-eafb198e3c0e",
    "Cake":            "7f2e1c52-84ad-46eb-9685-9e82788c99e4",
    "Coffee":          "4b2f5f47-f637-49be-a6a9-aac103622b2f",
    "GretchinWeiners": "993605b1-9e58-41f1-8115-b3e5c68bc7fc",
    "Limbo":           "7501ca6a-f9ea-4a46-addf-0073b43b5e60",
    "PaymentBypass":   "8ec42fb4-72d0-436f-b5cf-3851a53220a6",
    "SeaCafe":         "19e02494-8427-44b5-9c1b-98064b7e94e1",
    "SupplyCo":        "ef710ea4-417c-4c9c-987b-e8c647e2dcdc",
}

# Industry normalized to map via INDUSTRY_TO_SECTOR. Only applied where empty.
INDUSTRY = {
    "Bags": "construction", "Coffee": "hospitality", "SeaCafe": "retail",
    "Limbo": "manufacturing", "Bowls": "consulting", "Cake": "retail",
    "PaymentBypass": "finance", "SupplyCo": "warehousing",
    # GretchinWeiners already has 'Retail' (resolves) — left untouched.
}

# Additive recordables: (company, days_ago, days_away, days_restricted, classification, severity)
INCIDENTS = [
    # Gretchin Weiners 150 FTE — GOOD + milestones (180-day streak, DART-free yr, TRIR<bench).
    ("GretchinWeiners", 200, 0, 0, "medical_treatment", "low"),
    ("GretchinWeiners", 400, 6, 0, "days_away_from_work", "high"),
    ("GretchinWeiners", 500, 4, 0, "days_away_from_work", "medium"),
    ("GretchinWeiners", 600, 2, 0, "days_away_from_work", "medium"),
    # Limbo 25 FTE — 365-day incident-free streak + DART-free year (only a prior DART).
    ("Limbo", 400, 8, 0, "days_away_from_work", "high"),
    # Sea Cafe 100 FTE — push toward FAIR + a current DART case.
    ("SeaCafe", 40, 3, 0, "days_away_from_work", "medium"),
    ("SeaCafe", 150, 0, 0, "medical_treatment", "low"),
]

print("BEGIN;")
print()
print("-- 1. Fill industry ONLY where empty (benchmarks → bands + Premium Δ).")
for name, ind in INDUSTRY.items():
    print(f"UPDATE companies SET industry = '{ind}' "
          f"WHERE id = '{C[name]}' AND (industry IS NULL OR industry = '');")
print()
print("-- 2. Additive recordable incidents (tagged DEMO-REG-* for easy removal).")
cols = ("incident_number,title,incident_type,occurred_at,reported_by_name,reported_by_email,"
        "company_id,osha_recordable,osha_classification,days_away_from_work,days_restricted_duty,"
        "severity,status")
rows = []
for i, (name, days_ago, away, restr, cls, sev) in enumerate(INCIDENTS, start=1):
    rows.append(
        f"('DEMO-REG-{i}','Workplace injury (demo)','safety',"
        f"now() - interval '{days_ago} days','Demo Seed','reporter@example.com',"
        f"'{C[name]}',true,'{cls}',{away},{restr},'{sev}','closed')"
    )
print(f"INSERT INTO ir_incidents ({cols}) VALUES")
print(",\n".join(rows))
print("ON CONFLICT DO NOTHING;")
print()
print("COMMIT;")
