"""Cappe — website builder.

A separate product that runs on the matcha stack (same FastAPI app, Postgres,
JWT/password utility functions) but does NOT use matcha's tenant model. Cappe
identity lives in `cappe_accounts`; the router mounts at `/api/cappe` outside
matcha's feature-gate chain. See routes/__init__.py.
"""
