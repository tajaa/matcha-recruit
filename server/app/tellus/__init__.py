"""Tell-Us — standalone rewards-for-feedback app.

A separate product that runs on the matcha stack (same FastAPI app, Postgres
pool, JWT/password helpers) but does NOT use matcha's tenant model. Tell-Us
identity lives in `tellus_accounts`; the router mounts at `/api/tellus` outside
matcha's feature-gate chain. Mirrors the Cappe precedent (see app/cappe/).

Two sides share one identity table (`account_type`):
  - consumer — gives feedback, earns points, redeems in the city marketplace
  - brand    — mints store QR links, triages feedback, funds/lists rewards
"""
