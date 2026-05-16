"""Shared helpers for email submodules.

Holds the reserved-test-domain guard (defense in depth against bounce
storms from realistic-looking fake test data — see root CLAUDE.md
"Test Data — Email Domains" section) and any other cross-cutting
constants email mixins need.
"""

# RFC 2606 / RFC 6761 reserved domains — never deliverable, safe for test data.
# Hard-blocked at send time so test rows ending up in prod cannot cause bounce storms.
_RESERVED_EXAMPLE_DOMAINS = frozenset({"example.com", "example.org", "example.net"})
_RESERVED_TLDS = (".test", ".invalid", ".localhost", ".example")


def _is_reserved_test_domain(email_address: str) -> bool:
    if not email_address or "@" not in email_address:
        return False
    domain = email_address.rsplit("@", 1)[-1].strip().lower().rstrip(".")
    if not domain:
        return False
    if domain in _RESERVED_EXAMPLE_DOMAINS:
        return True
    return domain.endswith(_RESERVED_TLDS)
