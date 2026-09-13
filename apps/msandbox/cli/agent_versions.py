from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
import tempfile
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .state import ensure_roots, state_lock, state_root


AGENTS = {
    "CODEX_VERSION": ("@openai/codex", "CODEX_VERSION"),
    "CLAUDE_CODE_VERSION": ("@anthropic-ai/claude-code", "CLAUDE_CODE_VERSION"),
}
CACHE_FILE = "agent-versions.json"
VERSION_PATTERN = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.+_-]*$")


def _pinned_versions(runtime_root: Path) -> dict[str, str]:
    dockerfile = runtime_root / "docker/agent-sandbox/Dockerfile"
    contents = dockerfile.read_text(encoding="utf-8")
    versions: dict[str, str] = {}
    for environment_name, (_, argument_name) in AGENTS.items():
        match = re.search(rf"^ARG {re.escape(argument_name)}=([^\s#]+)", contents, re.MULTILINE)
        if not match:
            raise RuntimeError(f"missing {argument_name} default in {dockerfile}")
        versions[environment_name] = match.group(1)
    return versions


def _read_cache() -> dict[str, str]:
    try:
        raw = json.loads((state_root() / CACHE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    versions = raw.get("versions") if isinstance(raw, dict) else None
    if not isinstance(versions, dict):
        return {}
    return {
        name: value
        for name, value in versions.items()
        if name in AGENTS and isinstance(value, str) and VERSION_PATTERN.fullmatch(value)
    }


def _write_cache(versions: dict[str, str]) -> None:
    ensure_roots()
    path = state_root() / CACHE_FILE
    # Multiple session starts can resolve at once. A unique temporary file
    # plus the shared lock prevents one writer from replacing another's file.
    with state_lock("agent-version-cache"):
        descriptor, temporary_name = tempfile.mkstemp(prefix=".agent-versions.", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump({"schema_version": 1, "versions": versions}, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def _latest_version(package: str, timeout_seconds: float) -> str:
    encoded = package.replace("/", "%2F")
    request = urllib.request.Request(
        f"https://registry.npmjs.org/{encoded}/latest",
        headers={"Accept": "application/json", "User-Agent": "matcha-msandbox"},
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = json.load(response)
    version = payload.get("version") if isinstance(payload, dict) else None
    if not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version):
        raise RuntimeError(f"npm returned an invalid version for {package}")
    return version


def resolve_agent_versions(runtime_root: Path) -> dict[str, str]:
    """Resolve immutable image build args from npm, with offline-safe fallback.

    Explicit environment variables win. Setting MSANDBOX_AGENT_AUTO_UPDATE=0
    uses the Dockerfile defaults and avoids all registry traffic.
    """
    pinned = _pinned_versions(runtime_root)
    resolved = dict(pinned)
    cached = _read_cache()
    auto_update = os.environ.get("MSANDBOX_AGENT_AUTO_UPDATE", "1") != "0"
    timeout = float(os.environ.get("MSANDBOX_AGENT_VERSION_TIMEOUT_SECONDS", "3"))
    failures: list[str] = []

    unresolved = [name for name in AGENTS if not os.environ.get(name)]
    if auto_update and unresolved:
        with ThreadPoolExecutor(max_workers=len(unresolved)) as executor:
            requests = {
                executor.submit(_latest_version, AGENTS[name][0], timeout): name
                for name in unresolved
            }
            for future in as_completed(requests):
                name = requests[future]
                try:
                    resolved[name] = future.result()
                except (OSError, RuntimeError, ValueError, urllib.error.URLError) as exc:
                    resolved[name] = cached.get(name, pinned[name])
                    failures.append(f"{AGENTS[name][0]}: {exc}")

    for name in AGENTS:
        override = os.environ.get(name)
        if override:
            if not VERSION_PATTERN.fullmatch(override):
                raise RuntimeError(f"invalid {name}: {override!r}")
            resolved[name] = override

    if auto_update and not failures:
        _write_cache(resolved)
    elif failures:
        print(
            "Warning: could not check every agent release; using cached/pinned versions ("
            + "; ".join(failures)
            + ")",
            file=sys.stderr,
        )
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--shell", action="store_true")
    args = parser.parse_args(argv)
    versions = resolve_agent_versions(args.runtime_root.resolve())
    if args.shell:
        for name, value in versions.items():
            print(f"export {name}={shlex.quote(value)}")
    else:
        print(json.dumps(versions, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
