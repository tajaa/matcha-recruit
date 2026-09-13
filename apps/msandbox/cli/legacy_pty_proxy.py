from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

from .attachments import AttachmentError, DEFAULT_MAX_BYTES, DEFAULT_SESSION_MAX_BYTES
from .pty_proxy import rewrite_paste_stream_to_inbox, run_with_file_proxy


def _positive_limit(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise AttachmentError(f"{name} must be an integer") from exc
    if parsed <= 0:
        raise AttachmentError(f"{name} must be positive")
    return parsed


def _report_import_error(exc: Exception) -> None:
    print(
        f"\r\nmsandbox: attachment import failed: {exc}\r",
        file=sys.stderr,
        flush=True,
    )


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="msandbox-file-proxy")
    parser.add_argument("--inbox", required=True, type=Path)
    parser.add_argument("--container-dir", required=True, type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command is required after --")

    inbox = args.inbox.expanduser().resolve()
    lock_digest = hashlib.sha256(str(inbox).encode()).hexdigest()[:16]
    max_bytes = _positive_limit("MSANDBOX_ATTACHMENT_MAX_BYTES", DEFAULT_MAX_BYTES)
    session_max_bytes = _positive_limit(
        "MSANDBOX_ATTACHMENT_SESSION_MAX_BYTES",
        DEFAULT_SESSION_MAX_BYTES,
    )
    return run_with_file_proxy(
        command,
        lambda data: rewrite_paste_stream_to_inbox(
            data,
            inbox=inbox,
            container_dir=args.container_dir,
            lock_name=f"attachments-legacy-{lock_digest}",
            max_bytes=max_bytes,
            session_max_bytes=session_max_bytes,
            on_error=_report_import_error,
        ),
    )


def main() -> None:
    try:
        raise SystemExit(run())
    except AttachmentError as exc:
        print(f"msandbox: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
