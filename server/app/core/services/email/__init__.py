"""Email service package.

External callers continue to do:

    from app.core.services.email import EmailService, get_email_service, _is_reserved_test_domain

The package is split into:
- `client.py` — slim `EmailService` (transport + mixin composition) and
  `get_email_service()` singleton factory.
- `_shared.py` — reserved-domain guard.
- Per-domain mixin files (`auth.py`, `employee.py`, `candidate.py`,
  `compliance.py`, `training.py`, `misc.py`) each owning a slice of the
  send methods.

`EmailService` in `client.py` composes the mixins via multiple
inheritance. All 35 external importers see the same surface as the
original flat `email.py`.
"""
from .client import EmailService, get_email_service  # noqa: F401
from ._shared import _is_reserved_test_domain  # noqa: F401
