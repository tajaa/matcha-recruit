"""Recap unit tests never open a database, broker, provider or storage account."""
import os

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "recap-unit-tests-only")
