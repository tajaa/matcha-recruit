"""One definition of the Codex ``auth.json`` shape the suites build.

Three suites need the same fixture — two shell, one Python — and three copies
drift the moment the real file grows a field or renames a claim, leaving one
suite validating a shape production no longer writes. Python owns it; the
shell suites call the CLI below.

    python3 codex_auth_fixture.py PATH EXPIRY_EPOCH
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path


def _segment(payload: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()


def write_auth_fixture(path: Path | str, expiry_epoch: float) -> Path:
    """Write an auth.json whose access token carries ``exp``.

    The signature is a placeholder: nothing verifies it, and the preflight
    reads the ``exp`` claim only.
    """
    path = Path(path)
    token = ".".join(
        (_segment({"alg": "none"}), _segment({"exp": expiry_epoch}), "sig")
    )
    path.write_text(
        json.dumps({"tokens": {"access_token": token, "refresh_token": "r"}}),
        encoding="utf-8",
    )
    return path


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: codex_auth_fixture.py PATH EXPIRY_EPOCH", file=sys.stderr)
        return 2
    write_auth_fixture(argv[0], float(argv[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
