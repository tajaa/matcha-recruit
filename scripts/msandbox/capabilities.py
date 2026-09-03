"""Measured capability contract for one msandbox session.

The picker, `msandbox doctor`, and the agent's own injected context all read
exactly one registry. A capability is rendered available only when its probe
exercised the real boundary — never because an executable happens to exist.

Three capabilities are *denied* by design. Their probes assert the absence of a
broader identity; a probe that finds one reports ``available``, which is a
report failure rather than a green capability.

One capability — ``host_credentials`` — is the opposite: the repo checkout's own
secrets and the read-only ``~/.aws`` mount are reachable on purpose
(docs/ops/AGENT_SANDBOX.md). It is measured, rendered with a warning, and never
counted as a leak, because a boundary the design does not claim must not be
reported as one.

Probe output is redacted and truncated before it reaches this module's data
model. Tokens, passwords, PEM bodies, and URL credentials never enter a
capability report, its JSON/Markdown renderings, or the agent's context.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

from .docker_runtime import attachment_dir, compose_command, exec_in_session, session_home
from .models import CapabilityReport, CapabilityResult, CapabilityStatus, SessionRecord, utc_now
from .state import config_root, state_root


CAPABILITY_SCHEMA_VERSION = 1
REPORT_DIRECTORY = ".msandbox"
CONTAINER_REPORT_DIR = "/home/agent/.msandbox"
DEFAULT_TIMEOUT_S = 20.0
DETAIL_LIMIT = 160
STALE_AFTER_S = 900.0

# Where PR D/E/F deposit the purpose-built restricted identities. Their absence
# is the honest reason a production capability renders unavailable today.
PRODUCTION_TEST_DIR = "production-test"
PRODUCTION_TEST_ACCOUNTS = "accounts.json"
PRODUCTION_TEST_PG_SERVICE = "pg_service.conf"
PRODUCTION_TEST_SSH_KEY = "ssh/matcha-prod-test"
NATIVE_BUILDER_SOCKET = "native-builder.sock"
SANDBOX_AWS_PROFILE = "matcha-msandbox"
# The session's own view of the operator config directory. The host resolves the
# same directory through state.config_root(), which honours MSANDBOX_CONFIG_DIR;
# a container never sees that override, so the mount target is the one constant
# both sides are derived from.
CONTAINER_CONFIG_DIR = "/home/agent/.config/matcha-msandbox"

# Credentials nothing is supposed to mount. Their presence means a mount went
# wrong, so finding one is a real leak rather than a documented capability.
FORBIDDEN_CONTAINER_PATHS = (
    "/home/agent/.env.backend",
    "/home/agent/.ssh/roonMT-arm.pem",
    "/var/run/docker.sock",
)
# Broad host credentials an interactive session reaches *by design*: the repo
# bind mount carries whatever the host checkout holds, and ~/.aws is mounted
# read-only on purpose (docs/ops/AGENT_SANDBOX.md, "Threat model" — AutoPR
# narrows both through SANDBOX_WORKSPACE_DIR/SANDBOX_AWS_DIR). Calling these a
# leak would make every healthy interactive session red; the agent still has to
# know they are reachable, so they are measured and rendered as a warning.
DOCUMENTED_HOST_CREDENTIAL_PATHS = (
    "/workspace/secrets/roonMT-arm.pem",
    "/workspace/server/.env",
    "/workspace/deploy/.env.backend",
)
# Code signing and image push. None of these can exist in the Linux workspace
# image, which is exactly what this denial asserts. Deploy *dispatch* is not in
# this list: it rides the GitHub token, so `github` measures that authority
# instead of this probe claiming an absence it never checked.
CODE_SIGNING_PATHS = (
    "/var/run/docker.sock",
    "/home/agent/.docker/config.json",
    "/home/agent/Library/Keychains",
)


class CapabilityError(RuntimeError):
    pass


_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"-----BEGIN[^-]*PRIVATE KEY-----.*?-----END[^-]*-----", re.S), "[redacted key]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}"), "[redacted token]"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), "[redacted token]"),
    (re.compile(r"\b(?:AKIA|ASIA|AROA|AIDA)[0-9A-Z]{12,}"), "[redacted key id]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"), "[redacted token]"),
    (re.compile(r"\bey[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"), "[redacted jwt]"),
    (re.compile(r"(?i)\b(pass(?:word)?|secret|token|api[_-]?key)\b\s*[=:]\s*\S+"), r"\1=[redacted]"),
    (re.compile(r"(?i)\bbearer\s+\S+"), "bearer [redacted]"),
    # postgres://user:password@host — keep the shape, drop the credential.
    (re.compile(r"([a-z0-9+.-]+://)[^\s/@:]+:[^\s/@]+@"), r"\1[redacted]@"),
    # AWS account numbers inside an ARN identify a real account; the identity
    # name is what the probe actually needs to assert.
    (re.compile(r"(arn:aws[a-z-]*:[a-z0-9-]+:[a-z0-9-]*:)\d{12}"), r"\1[redacted]"),
)


def redact(text: str) -> str:
    """Strip credential-shaped substrings from probe output."""
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def summarize(text: str, *, limit: int = DETAIL_LIMIT) -> str:
    """Collapse probe output into one short, redacted, single-line detail."""
    collapsed = " ".join(redact(text or "").split())
    if len(collapsed) > limit:
        collapsed = collapsed[: limit - 1].rstrip() + "…"
    return collapsed


@dataclass(frozen=True)
class ProbeOutcome:
    status: CapabilityStatus
    detail: str


@dataclass
class ProbeContext:
    """Everything a probe may touch. Injected so tests never need Docker."""

    record: SessionRecord
    run_container: Callable[..., subprocess.CompletedProcess]
    run_host: Callable[..., subprocess.CompletedProcess]
    container_available: bool = True
    # Measurements two probes share. Without it every report pays for the
    # production database round trip twice.
    cache: dict[str, object] = field(default_factory=dict)

    def container(
        self,
        script: str,
        *,
        timeout: float = DEFAULT_TIMEOUT_S,
    ) -> subprocess.CompletedProcess:
        return self.run_container(
            self.record,
            ["bash", "-lc", script],
            tty=False,
            capture=True,
            timeout=timeout,
        )

    def host(
        self,
        argv: Sequence[str],
        *,
        timeout: float = DEFAULT_TIMEOUT_S,
    ) -> subprocess.CompletedProcess:
        return self.run_host(
            list(argv),
            check=False,
            text=True,
            capture_output=True,
            timeout=timeout,
        )


@dataclass(frozen=True)
class Probe:
    id: str
    title: str
    phase: str  # "host" or "container"
    run: Callable[[ProbeContext], ProbeOutcome]
    invocation: str | None = None
    required: bool = False
    denial: bool = False
    # Reachable by design, powerful, and policy-gated: rendered with a warning
    # and never counted as a leak.
    warning: bool = False
    # What the create screen may claim before anything is measured, as
    # (expected_available, note) or None for "measured after the session starts".
    plan: Callable[[bool, bool], "tuple[bool, str] | None"] | None = None


def _combined(completed: subprocess.CompletedProcess) -> str:
    return f"{completed.stdout or ''}\n{completed.stderr or ''}".strip()


def production_test_dir() -> Path:
    """Host side of the operator credential directory (honours the override)."""
    return config_root() / PRODUCTION_TEST_DIR


def _missing_production_credentials(name: str) -> bool:
    candidate = production_test_dir() / name
    return not (candidate.is_file() and not candidate.is_symlink())


# ---------------------------------------------------------------------------
# Container probes
# ---------------------------------------------------------------------------


# `set -e` is what makes the writability test load-bearing: a trailing
# `|| true` over the whole script would report a read-only workspace as an
# available capability. Only the detached-HEAD case may fail, and it is the
# last command, so the script still exits 0 for a detached worktree.
_REPO_SCRIPT = (
    "set -e\n"
    "probe=$(mktemp /workspace/.msandbox-write-probe.XXXXXX)\n"
    "trap 'rm -f \"$probe\"' EXIT\n"
    "git -C /workspace rev-parse --short HEAD\n"
    "git -C /workspace symbolic-ref -q HEAD || true\n"
)


def _probe_repo(context: ProbeContext) -> ProbeOutcome:
    completed = context.container(_REPO_SCRIPT)
    lines = [line for line in (completed.stdout or "").split() if line]
    if completed.returncode != 0 or not lines:
        return ProbeOutcome(
            "unavailable",
            summarize(_combined(completed)) or "the workspace is not writable",
        )
    head = lines[0]
    attached = any(line.startswith("refs/heads/") for line in lines)
    shape = "attached branch" if attached else "detached worktree"
    return ProbeOutcome("available", f"{shape} at {head}")


def _probe_linux_build(context: ProbeContext) -> ProbeOutcome:
    completed = context.container(
        "set -e\n"
        "python3 --version\n"
        "node --version\n"
        "npm --version\n"
        "server/venv/bin/python -m pytest --version\n"
        "client/node_modules/.bin/vitest --version\n",
        timeout=90.0,
    )
    if completed.returncode != 0:
        return ProbeOutcome("unavailable", summarize(_combined(completed)) or "toolchain probe failed")
    values = [line.strip() for line in (completed.stdout or "").splitlines() if line.strip()]
    labels = ("Python", "Node", "npm", "pytest", "Vitest")
    # Each tool prints its version differently, and some append the Node build
    # they run on. Take the first version-shaped token on the line.
    version = re.compile(r"\d+(?:\.\d+)+")
    detail = ", ".join(
        f"{label} {(version.search(value) or [value])[0]}"
        for label, value in zip(labels, values)
    )
    return ProbeOutcome("available", detail or "toolchain present")


def _dev_bind_script(ports: Iterable[int]) -> str:
    """Bind the dev ports and reach the shared database the capability claims."""
    return (
        "python3 - <<'PY'\n"
        "import socket, sys\n"
        f"ports = {tuple(int(port) for port in ports)!r}\n"
        "for port in ports:\n"
        "    probe = socket.socket()\n"
        "    try:\n"
        "        probe.bind(('0.0.0.0', port))\n"
        "    except OSError as error:\n"
        "        print('BUSY %d %s' % (port, error.strerror or error))\n"
        "        sys.exit(1)\n"
        "    finally:\n"
        "        probe.close()\n"
        "print('PORTS ok')\n"
        "try:\n"
        "    socket.create_connection(('host.docker.internal', 5432), 3).close()\n"
        "except OSError as error:\n"
        "    print('DB %s' % (error.strerror or error))\n"
        "else:\n"
        "    print('DB ok')\n"
        "PY\n"
    )


def _container_dev_ports() -> dict[str, int]:
    """What the dev stack binds *inside* the container.

    `record.ports` is the Mac-facing half of each mapping; compose publishes
    those onto the container-side defaults in docker-compose.sandbox-dev.yml.
    """
    defaults = (("backend", 8001), ("frontend", 5174), ("tellus", 5191), ("oceanlab", 5201))
    resolved: dict[str, int] = {}
    for name, fallback in defaults:
        try:
            resolved[name] = int(os.environ.get(f"{name.upper()}_PORT", fallback))
        except ValueError:
            resolved[name] = fallback
    return resolved


def _probe_isolated_dev(context: ProbeContext) -> ProbeOutcome:
    record = context.record
    if not record.dev:
        return ProbeOutcome("unavailable", "session was created without development tools")
    completed = context.container("test -x scripts/dev-remote.sh")
    if completed.returncode != 0:
        return ProbeOutcome("unavailable", "scripts/dev-remote.sh is missing or not executable")
    ports = record.ports
    if not ports:
        return ProbeOutcome("unavailable", "no development port block is assigned")
    inside = _container_dev_ports()
    bound = context.container(_dev_bind_script(inside.values()), timeout=45.0)
    if bound.returncode != 0:
        return ProbeOutcome(
            "unavailable",
            summarize(_combined(bound)) or "the development ports are not bindable",
        )
    values = [line.strip() for line in (bound.stdout or "").splitlines() if line.strip()]
    database = next((item[3:].strip() for item in values if item.startswith("DB ")), "unknown")
    # Publication is runtime state, not compose configuration: ask Docker what
    # this container actually exposes to the Mac, and hold it against the port
    # block the session record claims.
    published = context.host(
        compose_command(record, "port", "workspace", str(inside["backend"])),
        timeout=30.0,
    )
    mapping = [line.strip() for line in (published.stdout or "").splitlines() if line.strip()]
    if published.returncode != 0 or not mapping:
        return ProbeOutcome(
            "unavailable",
            summarize(_combined(published)) or "the dev ports are not published to the host",
        )
    if not mapping[0].endswith(f":{ports.backend}"):
        return ProbeOutcome(
            "unavailable",
            f"backend publishes at {summarize(mapping[0])}, not the recorded :{ports.backend}",
        )
    shared = "shared host database reachable" if database == "ok" else f"shared host database: {database}"
    return ProbeOutcome(
        "available",
        f"published at {mapping[0]}; frontend :{ports.frontend}, "
        f"Tell-Us :{ports.tellus}, Oceanlab :{ports.oceanlab}; {shared}",
    )


_BROWSER_SCRIPT = (
    "server/venv/bin/python - <<'PY'\n"
    "from playwright.sync_api import sync_playwright\n"
    "with sync_playwright() as play:\n"
    "    browser = play.chromium.launch()\n"
    "    print(browser.version)\n"
    "    browser.close()\n"
    "PY\n"
)


def _probe_browser(context: ProbeContext) -> ProbeOutcome:
    if not context.record.playwright:
        return ProbeOutcome("unavailable", "session image was built without the Playwright overlay")
    completed = context.container(_BROWSER_SCRIPT, timeout=120.0)
    if completed.returncode != 0:
        return ProbeOutcome("unavailable", summarize(_combined(completed)) or "Chromium did not launch")
    version = (completed.stdout or "").strip().splitlines()[-1:] or ["unknown"]
    return ProbeOutcome("available", f"Playwright Chromium {version[0]}")


def _probe_attachments(context: ProbeContext) -> ProbeOutcome:
    inbox = attachment_dir(context.record)
    try:
        inbox.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError as exc:
        return ProbeOutcome("unavailable", summarize(str(exc)))
    marker = inbox / f".capability-probe-{secrets.token_hex(6)}"
    try:
        marker.write_bytes(b"msandbox capability probe\n")
        marker.chmod(0o600)
        completed = context.container(f"test -r /attachments/{marker.name}")
    except OSError as exc:
        return ProbeOutcome("unavailable", summarize(str(exc)))
    finally:
        marker.unlink(missing_ok=True)
    if completed.returncode != 0:
        return ProbeOutcome("unavailable", "the session inbox is not readable inside the container")
    return ProbeOutcome("available", "bounded session inbox at /attachments")


def _probe_github(context: ProbeContext) -> ProbeOutcome:
    from .sessions import _github_repo

    try:
        repository = _github_repo(context.record.repo_path)
    except Exception as exc:  # Non-GitHub or unreadable remote is not a crash.
        return ProbeOutcome("unavailable", summarize(str(exc)))
    completed = context.container(
        "set -e\n"
        "gh auth status --hostname github.com >/dev/null\n"
        "gh api user --jq .login\n"
        f"gh api repos/{repository} "
        "--jq '\"\\(.full_name) push=\\(.permissions.push // false)"
        " admin=\\(.permissions.admin // false)\"'\n"
        f"gh workflow list --repo {repository} --limit 1 >/dev/null\n",
        timeout=45.0,
    )
    if completed.returncode != 0:
        return ProbeOutcome("unavailable", summarize(_combined(completed)) or "GitHub CLI is not authenticated")
    values = [line.strip() for line in (completed.stdout or "").splitlines() if line.strip()]
    login = values[0] if values else "unknown"
    permissions = values[1] if len(values) > 1 else ""
    # A token that can push can also dispatch deploy.yml and merge a pull
    # request. That is a policy boundary, not a credential one, so the report
    # says so instead of letting another capability claim it is denied.
    if "push=true" in permissions:
        authority = "push; workflow dispatch and merge are reachable — operator approval required"
    elif "push=false" in permissions:
        authority = "read-only; branches, dispatch, and merge are refused by GitHub"
    else:
        authority = "repository and Actions read; push authority not reported"
    return ProbeOutcome("available", f"{login} on {repository}; {authority}")


def _probe_aws(context: ProbeContext) -> ProbeOutcome:
    completed = context.container(
        f"AWS_PROFILE={SANDBOX_AWS_PROFILE} aws sts get-caller-identity --output json",
        timeout=45.0,
    )
    if completed.returncode != 0:
        return ProbeOutcome(
            "unavailable",
            f"the restricted {SANDBOX_AWS_PROFILE} profile is not provisioned",
        )
    try:
        identity = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return ProbeOutcome("unavailable", "AWS identity response was not valid JSON")
    arn = str(identity.get("Arn", ""))
    return ProbeOutcome("available", f"{summarize(arn)}; diagnostics only")


_PROD_TEST_DB_SCRIPT = (
    "set -e\n"
    "psql 'service=matcha_prod_test' -tAc 'select current_user'\n"
    "psql 'service=matcha_prod_test' -tAc "
    "\"select count(*) from companies where is_test is not true\"\n"
)


def _prod_test_db_measurement(context: ProbeContext) -> tuple[str, str, str] | None:
    """Return (role, non_test_visible_rows, raw_error) or None when unconfigured.

    Both `prod_test_db` and the `non_test_mutation` denial read this; the answer
    is cached per report so production is queried once, not twice.
    """
    if "prod_test_db" in context.cache:
        return context.cache["prod_test_db"]  # type: ignore[return-value]
    measurement = _prod_test_db_measure(context)
    context.cache["prod_test_db"] = measurement
    return measurement


def _prod_test_db_measure(context: ProbeContext) -> tuple[str, str, str] | None:
    if _missing_production_credentials(PRODUCTION_TEST_PG_SERVICE):
        return None
    completed = context.container(_PROD_TEST_DB_SCRIPT, timeout=45.0)
    values = [line.strip() for line in (completed.stdout or "").splitlines() if line.strip()]
    if completed.returncode != 0 or len(values) < 2:
        return ("", "", summarize(_combined(completed)) or "the restricted role did not answer")
    return (values[0], values[1], "")


def _probe_prod_test_db(context: ProbeContext) -> ProbeOutcome:
    measurement = _prod_test_db_measurement(context)
    if measurement is None:
        return ProbeOutcome(
            "unavailable",
            "no restricted production-test PostgreSQL service is configured on this host",
        )
    role, non_test, error = measurement
    if error:
        return ProbeOutcome("unavailable", error)
    if non_test != "0":
        return ProbeOutcome(
            "unavailable",
            f"{role} can see {non_test} non-test companies; the boundary is not installed",
        )
    return ProbeOutcome("available", f"{role}; live read/write, is_test enforced")


_PROD_TEST_API_SCRIPT = (
    "set -e\n"
    "server/venv/bin/python - <<'PY'\n"
    "import json, pathlib, urllib.request\n"
    f"root = pathlib.Path({CONTAINER_CONFIG_DIR!r}) / {PRODUCTION_TEST_DIR!r}\n"
    "config = json.loads((root / 'accounts.json').read_text())\n"
    "account = config['accounts'][0]\n"
    "password = (root / account['password_file']).read_text().strip()\n"
    "payload = json.dumps({'email': account['email'], 'password': password}).encode()\n"
    "request = urllib.request.Request(\n"
    "    config['base_url'].rstrip('/') + '/api/auth/login',\n"
    "    data=payload,\n"
    "    headers={'Content-Type': 'application/json'},\n"
    ")\n"
    "with urllib.request.urlopen(request, timeout=20) as response:\n"
    "    body = json.load(response)\n"
    "token = body['access_token']\n"
    "profile = urllib.request.Request(\n"
    "    config['base_url'].rstrip('/') + '/api/auth/me',\n"
    "    headers={'Authorization': 'Bearer ' + token},\n"
    ")\n"
    "with urllib.request.urlopen(profile, timeout=20) as response:\n"
    "    user = json.load(response)\n"
    "print(account['label'])\n"
    "print(bool(user.get('sandbox_test_only')))\n"
    "PY\n"
)


def _probe_prod_test_api(context: ProbeContext) -> ProbeOutcome:
    if _missing_production_credentials(PRODUCTION_TEST_ACCOUNTS):
        return ProbeOutcome(
            "unavailable",
            "no production-test account is configured on this host",
        )
    completed = context.container(_PROD_TEST_API_SCRIPT, timeout=60.0)
    values = [line.strip() for line in (completed.stdout or "").splitlines() if line.strip()]
    if completed.returncode != 0 or len(values) < 2:
        return ProbeOutcome("unavailable", summarize(_combined(completed)) or "the login probe failed")
    label, sandbox_only = values[-2], values[-1]
    if sandbox_only != "True":
        return ProbeOutcome(
            "unavailable",
            f"account {label} is not marked sandbox-test-only; refusing to advertise it",
        )
    return ProbeOutcome("available", f"account {label}; live read/write, is_test enforced")


def _probe_prod_diagnostics(context: ProbeContext) -> ProbeOutcome:
    if _missing_production_credentials(PRODUCTION_TEST_SSH_KEY):
        return ProbeOutcome(
            "unavailable",
            "no restricted production diagnostics key is configured on this host",
        )
    completed = context.container(
        "ssh -o BatchMode=yes -o StrictHostKeyChecking=yes "
        "-o ConnectTimeout=10 matcha-prod-test true",
        timeout=45.0,
    )
    if completed.returncode != 0:
        return ProbeOutcome("unavailable", summarize(_combined(completed)) or "the restricted host refused the key")
    return ProbeOutcome("available", "restricted SSH/log access; forwarding only")


# ---------------------------------------------------------------------------
# Denial probes — a finding here is a report failure, not a capability
# ---------------------------------------------------------------------------


def _probe_non_test_mutation(context: ProbeContext) -> ProbeOutcome:
    measurement = _prod_test_db_measurement(context)
    if measurement is None:
        return ProbeOutcome("denied", "no production database identity is provisioned")
    role, non_test, error = measurement
    if error:
        return ProbeOutcome("denied", "the restricted role cannot reach production")
    if non_test != "0":
        return ProbeOutcome(
            "available",
            f"{role} can see {non_test} non-test companies",
        )
    return ProbeOutcome("denied", "denied by API and PostgreSQL")


def _absent_paths_script(paths: Iterable[str]) -> str:
    checks = "\n".join(f'test -e {path} && echo "LEAK {path}"' for path in paths)
    return f"{checks}\nexit 0\n"


def _reachable_paths(context: ProbeContext, paths: Iterable[str]) -> list[str]:
    completed = context.container(_absent_paths_script(paths))
    return [
        line.split(maxsplit=1)[1]
        for line in (completed.stdout or "").splitlines()
        if line.startswith("LEAK ")
    ]


# Presence of an AWS profile name is configuration, not authority. Ask STS which
# profiles actually authenticate, with retries clamped so an unusable profile
# costs one refused call instead of a stalled report.
_AWS_PROFILE_SCRIPT = (
    "export AWS_RETRY_MODE=standard AWS_MAX_ATTEMPTS=1\n"
    "export AWS_METADATA_SERVICE_NUM_ATTEMPTS=1 AWS_METADATA_SERVICE_TIMEOUT=1\n"
    "aws configure list-profiles 2>/dev/null | head -5 | while read -r profile; do\n"
    f"  [ \"$profile\" = '{SANDBOX_AWS_PROFILE}' ] && continue\n"
    '  aws sts get-caller-identity --profile "$profile" >/dev/null 2>&1 '
    '&& echo "AWS $profile"\n'
    "done\n"
    "exit 0\n"
)


def _authenticating_aws_profiles(context: ProbeContext) -> list[str]:
    if "aws_profiles" in context.cache:
        return list(context.cache["aws_profiles"])  # type: ignore[arg-type]
    completed = context.container(_AWS_PROFILE_SCRIPT, timeout=60.0)
    profiles = [
        line.split(maxsplit=1)[1]
        for line in (completed.stdout or "").splitlines()
        if line.startswith("AWS ")
    ]
    context.cache["aws_profiles"] = profiles
    return profiles


def _probe_prod_admin(context: ProbeContext) -> ProbeOutcome:
    # Only paths nothing is supposed to mount. The documented repo and ~/.aws
    # mounts are measured by `host_credentials`; calling them a leak here made
    # every correctly-provisioned interactive session fail its own doctor.
    found = _reachable_paths(context, FORBIDDEN_CONTAINER_PATHS)
    if found:
        return ProbeOutcome("available", "reachable: " + summarize(", ".join(found)))
    return ProbeOutcome("denied", "no undocumented host administrative credential is mounted")


def _probe_host_credentials(context: ProbeContext) -> ProbeOutcome:
    """The broad identity an interactive session reaches on purpose."""
    found = _reachable_paths(context, DOCUMENTED_HOST_CREDENTIAL_PATHS)
    profiles = _authenticating_aws_profiles(context)
    if profiles:
        found.append(f"host AWS profile(s) {','.join(sorted(profiles)[:3])}")
    if not found:
        return ProbeOutcome(
            "unavailable",
            "no host credential is reachable; this session is narrowed to its own identity",
        )
    return ProbeOutcome(
        "available",
        summarize(", ".join(found)) + " — powerful and operator-gated, not a free-for-all",
    )


def _probe_code_signing(context: ProbeContext) -> ProbeOutcome:
    completed = context.container(
        _absent_paths_script(CODE_SIGNING_PATHS)
        + "command -v codesign >/dev/null && echo 'LEAK codesign'\n"
        + "command -v security >/dev/null && echo 'LEAK security'\n"
        + "exit 0\n"
    )
    leaks = [line.split(maxsplit=1)[1] for line in (completed.stdout or "").splitlines() if line.startswith("LEAK ")]
    if leaks:
        return ProbeOutcome("available", "reachable: " + summarize(", ".join(leaks)))
    return ProbeOutcome(
        "denied",
        "no keychain, signing identity, or Docker daemon in the Linux workspace",
    )


# ---------------------------------------------------------------------------
# Host probes
# ---------------------------------------------------------------------------


def native_builder_socket() -> Path:
    return state_root() / NATIVE_BUILDER_SOCKET


def _broker_socket_answers(socket_path: Path) -> tuple[bool, str]:
    """Connect to the builder socket. A socket file alone proves nothing."""
    import socket as socket_module

    client = socket_module.socket(socket_module.AF_UNIX, socket_module.SOCK_STREAM)
    client.settimeout(2.0)
    try:
        client.connect(str(socket_path))
    except OSError as error:
        return False, error.strerror or str(error)
    finally:
        client.close()
    return True, ""


def _probe_xcode(context: ProbeContext) -> ProbeOutcome:
    socket_path = native_builder_socket()
    if socket_path.exists() and not socket_path.is_symlink():
        answered, reason = _broker_socket_answers(socket_path)
        if not answered:
            return ProbeOutcome(
                "unavailable",
                summarize(f"the builder broker socket is stale: {reason}"),
            )
        completed = context.host(["xcodebuild", "-version"], timeout=60.0)
        if completed.returncode == 0:
            version = " ".join((completed.stdout or "").split()[:2]) or "Xcode"
            return ProbeOutcome("available", f"isolated local macOS builder answered, {version}")
        return ProbeOutcome("unavailable", summarize(_combined(completed)) or "xcodebuild failed")
    try:
        completed = context.host(["xcodebuild", "-version"], timeout=60.0)
    except FileNotFoundError:
        return ProbeOutcome(
            "unavailable",
            "no local Xcode; fall back to the ci.yml native-builds job on a pull request",
        )
    if completed.returncode != 0:
        return ProbeOutcome(
            "unavailable",
            "no usable local Xcode; fall back to the ci.yml native-builds job on a pull request",
        )
    version = " ".join((completed.stdout or "").split()[:2]) or "Xcode"
    return ProbeOutcome(
        "unavailable",
        f"{version} is installed but the isolated builder broker is not; "
        "an operator can run msandbox test SESSION --pr --xcode affected",
    )


# Every rendering of a capability — the picker, the CLI, the create screen's
# plan, and the agent's own context — is derived from this tuple. `plan` is what
# the create screen may claim before anything has been measured; None means the
# capability is only known after the session starts.
PROBES: tuple[Probe, ...] = (
    Probe(
        "repo_rw",
        "Repository read/write",
        "container",
        _probe_repo,
        invocation="git status; edit files under /workspace",
        required=True,
        plan=lambda dev, playwright: (True, "detached worktree"),
    ),
    Probe(
        "linux_build",
        "Linux build tools",
        "container",
        _probe_linux_build,
        invocation="server/venv/bin/python -m pytest; client/node_modules/.bin/vitest run",
        required=True,
        plan=lambda dev, playwright: (True, "Python, Node, npm, pytest, Vitest"),
    ),
    Probe(
        "isolated_dev",
        "Isolated development",
        "container",
        _probe_isolated_dev,
        invocation="./scripts/dev-remote.sh",
        plan=lambda dev, playwright: (
            (True, "backend, worker, Vite, Tell-Us, Oceanlab")
            if dev
            else (False, "choose Development to publish dev ports")
        ),
    ),
    Probe(
        "browser",
        "Headless browser",
        "container",
        _probe_browser,
        invocation="server/venv/bin/python -m playwright ...; sync_playwright().chromium.launch()",
        plan=lambda dev, playwright: (
            (True, "Playwright Chromium")
            if playwright
            else (False, "choose Development + browser")
        ),
    ),
    Probe(
        "attachments",
        "Image/PDF attachments",
        "container",
        _probe_attachments,
        invocation="read the files the operator drops in /attachments",
        plan=lambda dev, playwright: (True, "bounded session inbox"),
    ),
    Probe(
        "github",
        "GitHub CLI",
        "container",
        _probe_github,
        invocation="gh pr view; gh pr create --draft; gh run list",
        required=True,
        plan=lambda dev, playwright: (True, "branch/PR/checks; deploy stays operator-gated"),
    ),
    Probe(
        "aws",
        "AWS CLI",
        "container",
        _probe_aws,
        invocation="aws sts get-caller-identity",
    ),
    Probe(
        "prod_test_api",
        "Production test API",
        "container",
        _probe_prod_test_api,
        invocation="curl/Playwright against $PROD_TEST_BASE_URL with the session credential file",
    ),
    Probe(
        "prod_test_db",
        "Production test database",
        "container",
        _probe_prod_test_db,
        invocation="psql 'service=matcha_prod_test'",
    ),
    Probe(
        "prod_diagnostics",
        "Production diagnostics",
        "container",
        _probe_prod_diagnostics,
        invocation="ssh matcha-prod-test",
    ),
    Probe(
        "xcode",
        "Xcode",
        "host",
        _probe_xcode,
        invocation="msandbox native build espresso",
    ),
    Probe(
        "host_credentials",
        "Host credentials in reach",
        "container",
        _probe_host_credentials,
        invocation="the repo checkout's own secrets and the read-only ~/.aws mount",
        warning=True,
        plan=lambda dev, playwright: (
            True,
            "repo secrets and the read-only host AWS mount — operator-gated",
        ),
    ),
    Probe(
        "non_test_mutation",
        "Non-test tenant mutation",
        "container",
        _probe_non_test_mutation,
        denial=True,
        plan=lambda dev, playwright: (False, "denied by API and PostgreSQL"),
    ),
    Probe(
        "prod_admin",
        "Production admin/secrets",
        "container",
        _probe_prod_admin,
        denial=True,
        plan=lambda dev, playwright: (False, "no undocumented credential is mounted"),
    ),
    Probe(
        "code_signing",
        "Code signing / image push",
        "container",
        _probe_code_signing,
        denial=True,
        plan=lambda dev, playwright: (False, "no keychain or Docker daemon in the image"),
    ),
)


def probe_registry() -> tuple[Probe, ...]:
    return PROBES


def _run_probe(probe: Probe, context: ProbeContext) -> CapabilityResult:
    """Never let one probe abort the report; an error is an honest unavailable."""
    if probe.phase == "container" and not context.container_available:
        outcome = ProbeOutcome(
            "denied" if probe.denial else "unavailable",
            "the session container is not running",
        )
    else:
        try:
            outcome = probe.run(context)
        except subprocess.TimeoutExpired:
            outcome = ProbeOutcome(
                "denied" if probe.denial else "unavailable",
                "the probe exceeded its timeout",
            )
        except (OSError, ValueError, TypeError, KeyError, RuntimeError, json.JSONDecodeError) as exc:
            outcome = ProbeOutcome(
                "denied" if probe.denial else "unavailable",
                summarize(f"{type(exc).__name__}: {exc}"),
            )
    return CapabilityResult(
        id=probe.id,
        title=probe.title,
        status=outcome.status,
        detail=summarize(outcome.detail),
        invocation=probe.invocation,
    )


def collect_report(
    record: SessionRecord,
    *,
    run_container: Callable[..., subprocess.CompletedProcess] | None = None,
    run_host: Callable[..., subprocess.CompletedProcess] | None = None,
    container_available: bool = True,
) -> CapabilityReport:
    context = ProbeContext(
        record=record,
        run_container=run_container or exec_in_session,
        run_host=run_host or subprocess.run,
        container_available=container_available,
    )
    results = tuple(_run_probe(probe, context) for probe in probe_registry())
    return CapabilityReport(
        schema_version=CAPABILITY_SCHEMA_VERSION,
        session_id=record.id,
        results=results,
        checked_at=utc_now(),
        # Recorded so a cached report is never reused across a stop or start:
        # age alone cannot tell the picker the container went away.
        container_available=container_available,
    )


# ---------------------------------------------------------------------------
# Rendering and persistence
# ---------------------------------------------------------------------------


def _probe_by_id() -> dict[str, Probe]:
    return {probe.id: probe for probe in probe_registry()}


def _denial_ids() -> frozenset[str]:
    return frozenset(probe.id for probe in probe_registry() if probe.denial)


def _warning_ids() -> frozenset[str]:
    return frozenset(probe.id for probe in probe_registry() if probe.warning)


def _required_ids() -> frozenset[str]:
    return frozenset(probe.id for probe in probe_registry() if probe.required)


def leaks(report: CapabilityReport) -> tuple[CapabilityResult, ...]:
    """Denied-by-design capabilities whose probe found a usable identity."""
    denials = _denial_ids()
    return tuple(item for item in report.results if item.id in denials and item.status == "available")


def missing_required(report: CapabilityReport) -> tuple[CapabilityResult, ...]:
    required = _required_ids()
    return tuple(item for item in report.results if item.id in required and item.status != "available")


def report_ok(report: CapabilityReport) -> bool:
    return not leaks(report) and not missing_required(report)


def _icon(result: CapabilityResult, denials: frozenset[str], warnings: frozenset[str]) -> str:
    if result.id in denials or result.id in warnings:
        return "⚠️" if result.status == "available" else "❌"
    return "✅" if result.status == "available" else "❌"


def render_lines(report: CapabilityReport, *, name: str) -> list[str]:
    denials = _denial_ids()
    warnings = _warning_ids()
    # A report with no results is a truncated or hand-edited file, not a crash.
    width = max((len(item.title) for item in report.results), default=0) + 2
    lines = [f"Capabilities for {name}"]
    for result in report.results:
        icon = _icon(result, denials, warnings)
        detail = result.detail
        if result.id in denials and result.status == "available":
            detail = f"LEAK — {detail}"
        lines.append(f"  {icon} {result.title:<{width}}{detail}")
    if not report.results:
        lines.append("  no capability was measured; run `msandbox doctor` to remeasure")
    return lines


def render_report_text(report: CapabilityReport | None, *, name: str) -> str:
    """The exact block both `msandbox capabilities` and the picker display."""
    if report is None:
        return f"Capabilities for {name} could not be measured."
    lines: list[str] = []
    # Rows and results are parallel, except for the trailing note render_lines
    # adds when a report carries no results at all.
    rows = render_lines(report, name=name)[1:]
    for index, row in enumerate(rows):
        lines.append(row)
        result = report.results[index] if index < len(report.results) else None
        if result is not None and result.invocation and result.status == "available":
            lines.append(f"       invoke: {result.invocation}")
    lines.insert(0, f"Capabilities for {name}")
    for result in missing_required(report):
        lines.append(f"  required capability unavailable: {result.title} — {result.detail}")
    for result in leaks(report):
        lines.append(f"  LEAK: {result.title} — {result.detail}")
    return "\n".join(lines)


def render_markdown(report: CapabilityReport, *, name: str) -> str:
    denials = _denial_ids()
    parts = [
        f"# Session capabilities — {name}",
        "",
        "This capability report was measured for this session. Test the named "
        "invocation before claiming the capability is absent.",
        "",
        f"Measured at {report.checked_at}.",
        "",
        "## Available",
        "",
    ]
    warnings = _warning_ids()
    available = [
        item
        for item in report.results
        if item.id not in denials and item.id not in warnings and item.status == "available"
    ]
    if available:
        parts.append("| Capability | Detail | How to invoke |")
        parts.append("| --- | --- | --- |")
        for item in available:
            parts.append(f"| {item.title} | {item.detail} | `{item.invocation or 'n/a'}` |")
    else:
        parts.append("None measured available in this session.")
    parts.extend(["", "## Unavailable", ""])
    unavailable = [
        item
        for item in report.results
        if item.id not in denials and item.id not in warnings and item.status != "available"
    ]
    if unavailable:
        parts.append("| Capability | Why | Fallback |")
        parts.append("| --- | --- | --- |")
        for item in unavailable:
            parts.append(f"| {item.title} | {item.detail} | `{item.invocation or 'n/a'}` |")
    else:
        parts.append("Every non-denied capability is available.")
    reachable = [item for item in report.results if item.id in warnings and item.status == "available"]
    if reachable:
        parts.extend(["", "## Reachable by design — operator-gated", ""])
        for item in reachable:
            parts.append(f"- **{item.title}** — {item.detail}")
        parts.extend(
            [
                "",
                "These are mounted deliberately and are powerful. Read them only "
                "when the task needs them, never copy a credential into a file, a "
                "commit, or this conversation, and ask the operator before any "
                "action that changes production, deploys, or merges.",
            ]
        )
    parts.extend(["", "## Intentionally denied", ""])
    for item in report.results:
        if item.id not in denials:
            continue
        marker = "LEAK — " if item.status == "available" else ""
        parts.append(f"- **{item.title}** — {marker}{item.detail}")
    parts.extend(
        [
            "",
            "Denied capabilities are not oversights. Do not attempt to obtain a "
            "broader credential, and do not tell the user a denied action merely "
            "needs retrying.",
            "",
            "Deploying and merging are gated by policy, not by this list. If the "
            "GitHub row above reports push authority, `gh workflow run` and "
            "`gh pr merge` would succeed — which is exactly why they need the "
            "operator's word first. Open a draft pull request and stop there.",
            "",
        ]
    )
    return "\n".join(parts)


def report_paths(record: SessionRecord) -> tuple[Path, Path]:
    directory = session_home(record) / REPORT_DIRECTORY
    return directory / "capabilities.json", directory / "capabilities.md"


def container_report_paths() -> tuple[str, str]:
    return (
        f"{CONTAINER_REPORT_DIR}/capabilities.json",
        f"{CONTAINER_REPORT_DIR}/capabilities.md",
    )


def atomic_write(path: Path, payload: str) -> None:
    """Publish a mode-600 file without a predictable temp name or symlink hop."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.parent / f".{path.name}.{secrets.token_hex(6)}"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_report(record: SessionRecord, report: CapabilityReport) -> Path:
    """Persist the report as mode-600 JSON and Markdown under the session home."""
    json_path, markdown_path = report_paths(record)
    atomic_write(json_path, json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n")
    atomic_write(markdown_path, render_markdown(report, name=record.name))
    return json_path


def load_report(record: SessionRecord) -> CapabilityReport | None:
    json_path, _ = report_paths(record)
    if json_path.is_symlink() or not json_path.is_file():
        return None
    try:
        return CapabilityReport.from_dict(json.loads(json_path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def report_is_stale(report: CapabilityReport | None, *, max_age_s: float = STALE_AFTER_S) -> bool:
    if report is None:
        return True
    from datetime import datetime, timezone

    try:
        checked = datetime.fromisoformat(report.checked_at)
    except ValueError:
        return True
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - checked).total_seconds() > max_age_s


def planned_capabilities(*, dev: bool, playwright: bool) -> list[str]:
    """What a not-yet-created session expects to measure. Never a promise.

    Derived from `probe_registry()` so a new or renamed capability cannot leave
    a hand-maintained second list behind.
    """
    registry = probe_registry()
    width = max((len(probe.title) for probe in registry), default=0) + 2
    lines: list[str] = []
    deferred: list[str] = []
    for probe in registry:
        expectation = probe.plan(dev, playwright) if probe.plan else None
        if expectation is None:
            deferred.append(probe.title)
            continue
        expected, note = expectation
        if probe.denial or probe.warning:
            icon = "⚠️" if expected else "❌"
        else:
            icon = "✅" if expected else "❌"
        lines.append(f"  {icon} {probe.title:<{width}}{note}")
    if deferred:
        lines.extend(
            [
                "",
                f"{', '.join(deferred)} are measured after the session starts.",
            ]
        )
    return lines
