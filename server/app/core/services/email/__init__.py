"""Email service package.

External callers continue to do:

    from app.core.services.email import EmailService, get_email_service, _is_reserved_test_domain

The package is split into per-domain mixins (see `auth.py`, `employee.py`,
`candidate.py`, `compliance.py`, `training.py`, `misc.py`). The
`EmailService` class in `client.py` composes them via multiple
inheritance. All 35 external importers see the same surface as the
original flat `email.py`.
"""
# During migration, the symbols still live in _legacy.py and are re-exported
# from here. As each mixin migrates out, flip its source on the lines below.
from ._legacy import (  # noqa: F401
    EmailService,
    get_email_service,
)
from ._shared import _is_reserved_test_domain  # noqa: F401
