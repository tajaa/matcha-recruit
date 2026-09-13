"""Is the runner's Codex login usable, before anything is spent on it.

Every AutoPR lane copies the host's ``~/.codex/auth.json`` into its sandbox and
bind-mounts it read-only. Two facts make an expired access token fatal rather
than merely stale: the copy cannot persist a refresh, and the ChatGPT refresh
token is single-use, so the first run after expiry consumes it for everyone
and the file is dead until a human runs ``codex login``. Before this check a
dead token claimed a card (moved it to In Progress), paid a full workflow
prelude, died in seconds at ``codex exec``, and struck the card's failure
ledger for a fault that was never the card's.

The access token is a JWT; its ``exp`` claim is read here without verifying
the signature, which is all a preflight needs.

Also runnable as a script (the harness does that from bash):

    python3 codex_auth.py check [PATH]   # exit 0 ok, 4 login required
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

AUTH_REQUIRED_EXIT = 4
DEFAULT_MINIMUM_SECONDS = 300
FIX = "run `codex login` on the runner Mac, then start the lane again"


def default_auth_path() -> Path:
    configured = os.environ.get("AUTOPR_HOST_CODEX_AUTH_FILE")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".codex" / "auth.json"


def minimum_seconds() -> int:
    raw = os.environ.get("AUTOPR_CODEX_AUTH_MIN_SECONDS", "")
    return int(raw) if raw.isdigit() else DEFAULT_MINIMUM_SECONDS


def _jwt_claims(token: str) -> dict | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload.encode("ascii"))
        claims = json.loads(decoded)
    except (binascii.Error, ValueError, UnicodeError):
        return None
    return claims if isinstance(claims, dict) else None


def access_token_expiry(path: Path) -> datetime | None:
    """When the stored access token stops working, or None if unreadable.

    None covers every shape that cannot be checked — missing file, not JSON,
    no token, no ``exp`` — because a preflight must treat "cannot prove it
    works" exactly like "known dead".
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    tokens = data.get("tokens") if isinstance(data, dict) else None
    token = tokens.get("access_token") if isinstance(tokens, dict) else None
    claims = _jwt_claims(token) if isinstance(token, str) else None
    expiry = claims.get("exp") if claims else None
    if not isinstance(expiry, (int, float)) or isinstance(expiry, bool):
        return None
    return datetime.fromtimestamp(expiry, timezone.utc)


def check(
    path: Path | None = None,
    *,
    minimum: int | None = None,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """(usable, one-line message) for the login at ``path``."""
    path = path or default_auth_path()
    minimum = minimum_seconds() if minimum is None else minimum
    now = now or datetime.now(timezone.utc)
    expiry = access_token_expiry(path)
    if expiry is None:
        return False, f"codex login: no usable access token in {path}; {FIX}"
    remaining = int((expiry - now).total_seconds())
    stamp = expiry.astimezone().strftime("%Y-%m-%d %H:%M %Z")
    if remaining < minimum:
        state = "EXPIRED" if remaining <= 0 else f"expires in {remaining}s"
        return False, f"codex login: {state} ({stamp}); {FIX}"
    hours = remaining // 3600
    return True, f"codex login: expires {stamp} ({hours}h left)"


def main(argv: list[str]) -> int:
    if not argv or argv[0] != "check" or len(argv) > 2:
        print("usage: codex_auth.py check [AUTH_JSON]", file=sys.stderr)
        return 2
    path = Path(argv[1]).expanduser() if len(argv) == 2 else None
    usable, message = check(path)
    print(message, file=sys.stdout if usable else sys.stderr)
    return 0 if usable else AUTH_REQUIRED_EXIT


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
