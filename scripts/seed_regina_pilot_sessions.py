#!/usr/bin/env python3
"""Seed one Broker Pilot session per starter template ("mode") for the demo
broker 'Regina George LLC' (ashVidales+regina@gmail.com).

Each session is opened in a different mode against a client that makes the mode
legible (a construction prospect for the appetite read, a manufacturer with
platform loss development for the loss-run dive, and so on). The sessions are
EMPTY — no messages — so opening one shows the mode title plus the
mode-tailored starter prompts from services/broker_pilot.py:PILOT_TEMPLATES;
clicking a starter runs a real grounded turn.

Requires the brokerpilot02 column:
    ALTER TABLE broker_pilot_sessions ADD COLUMN IF NOT EXISTS template_key VARCHAR(40);

Run:  python3 scripts/seed_regina_pilot_sessions.py \
        | docker exec -i -e PGPASSWORD=matcha_dev matcha-postgres psql -U matcha -d matcha
Undo: DELETE FROM broker_pilot_sessions WHERE id::text LIKE 'd0000002-%';
"""

BROKER_ID = "574c50d6-e3d2-4bef-a4d7-4e153b6da053"   # Regina George LLC
CREATED_BY = "fb7b0bbc-5cad-4a4d-aac0-90b9f8e09566"  # ashVidales+regina@gmail.com

# (template_key, session title, subject_kind, subject_id, client name, updated_days_ago)
# Titles follow the route's derivation: "<template title> — <client>".
# Each client is chosen because it HOLDS the data the mode grounds on — a mode
# pointed at a client with an empty corpus produces an honest refusal, not a demo.
SESSIONS = [
    # coverage lines + two parsed contracts with extracted indemnity clauses
    ("contract_review", "company",  "1a1123e5-4c24-4735-8501-9a64a1dd7691",
     "720 Behavioral", 1),
    # WC metrics + incidents (At Risk band, EMR on file)
    ("mid_year", "company",         "19e02494-8427-44b5-9c1b-98064b7e94e1",
     "Sea Cafe", 3),
    # wc_loss_runs across 3 valuations + EMR
    ("renewal_90", "company",       "993605b1-9e58-41f1-8115-b3e5c68bc7fc",
     "Bear Co.", 5),
    # wc_loss_runs + an uploaded loss-run CSV (see seed_regina_pilot_docs.py)
    ("loss_run", "company",         "3e69de7a-0c0e-4a34-ab7b-3e9462756516",
     "Bags", 8),
    # off-platform prospect, Critical WC band — the appetite story
    ("new_business", "external",    "b0000001-0000-0000-0000-000000000003",
     "Summit Builders", 12),
    # two uploaded carrier quotes (see seed_regina_pilot_docs.py)
    ("quote_comparison", "external", "b0000001-0000-0000-0000-000000000002",
     "Brightline Retail Co", 16),
]

# Mode titles, copied from PILOT_TEMPLATES (keep in sync if the catalog changes).
TITLES = {
    "contract_review": "Contract review",
    "mid_year": "Mid-year check-in",
    "renewal_90": "90-day renewal check-in",
    "new_business": "New business appetite read",
    "loss_run": "Loss-run deep dive",
    "quote_comparison": "Quote comparison",
}

print("BEGIN;")
print()
print("-- Broker Pilot starter-mode sessions for Regina George LLC (DEMO, tagged d0000002-*).")
cols = ("id,broker_id,subject_kind,subject_id,title,template_key,status,created_by,"
        "created_at,updated_at")
rows = []
for i, (key, kind, subject_id, client, days) in enumerate(SESSIONS, start=1):
    title = f"{TITLES[key]} — {client}".replace("'", "''")
    rows.append(
        f"('d0000002-0000-0000-0000-{i:012d}','{BROKER_ID}','{kind}','{subject_id}',"
        f"'{title}','{key}','active','{CREATED_BY}',"
        f"now() - interval '{days} days', now() - interval '{days} days')"
    )
print(f"INSERT INTO broker_pilot_sessions ({cols}) VALUES")
print(",\n".join(rows))
print("ON CONFLICT (id) DO NOTHING;")
print()
print("COMMIT;")
