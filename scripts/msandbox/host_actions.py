from __future__ import annotations

import json
import os
import subprocess
import time
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .models import CommandResult, SessionRecord
from .state import data_root, list_sessions, load_session


XcodeTarget = Literal["espresso", "matchatutor", "tellus", "gummfit"]
XcodeAction = Literal["build", "test"]


@dataclass(frozen=True)
class XcodeDefinition:
    project: str
    scheme: str
    platform: Literal["macos", "ios"]


XCODE_TARGETS: dict[str, XcodeDefinition] = {
    "espresso": XcodeDefinition("platforms/desktop/Espresso/Matcha.xcodeproj", "Matcha", "macos"),
    "matchatutor": XcodeDefinition("platforms/ios/MatchaTutor/MatchaTutor.xcodeproj", "MatchaTutor", "ios"),
    "tellus": XcodeDefinition("platforms/ios/TellUs/TellUs.xcodeproj", "TellUs", "ios"),
    "gummfit": XcodeDefinition("platforms/ios/Gummfit/Gummfit.xcodeproj", "Gummfit", "ios"),
}


class HostActionError(RuntimeError):
    pass


def _read_request(path: Path) -> dict:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise HostActionError(f"unsafe host request: {path.name}: {exc}") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise HostActionError(f"host request is not a regular file: {path.name}")
        with os.fdopen(descriptor, encoding="utf-8", closefd=False) as handle:
            return json.load(handle)
    finally:
        os.close(descriptor)


def _write_json_atomic(path: Path, payload: dict) -> None:
    """Replace, never follow, a container-controlled result path."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".result.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def affected_xcode_targets(paths: list[str] | tuple[str, ...]) -> set[str]:
    mapping = {
        "platforms/desktop/Espresso/": "espresso",
        "platforms/ios/MatchaTutor/": "matchatutor",
        "platforms/ios/TellUs/": "tellus",
        "platforms/ios/Gummfit/": "gummfit",
    }
    affected = set()
    for path in paths:
        for prefix, target in mapping.items():
            if path.startswith(prefix):
                affected.add(target)
    return affected


def build_xcode_command(
    session: SessionRecord,
    target: str,
    action: str,
) -> tuple[list[str], Path, Path]:
    """Build an allowlisted argv; arbitrary host commands never enter this boundary."""
    if target not in XCODE_TARGETS:
        raise HostActionError(f"unknown Xcode target: {target}")
    if action not in ("build", "test"):
        raise HostActionError(f"unknown Xcode action: {action}")
    definition = XCODE_TARGETS[target]
    worktree = session.worktree.resolve()
    project = (worktree / definition.project).resolve()
    if worktree not in project.parents or not project.is_dir():
        raise HostActionError(f"Xcode project is outside the registered worktree: {project}")
    derived_data = data_root() / "xcode-derived-data" / session.id / target
    derived_data.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = (
        "platform=macOS"
        if definition.platform == "macos"
        else os.environ.get(
            "MSANDBOX_IOS_DESTINATION",
            "platform=iOS Simulator,name=iPhone 16",
        )
    )
    argv = [
        "xcodebuild",
        "-project",
        str(project),
        "-scheme",
        definition.scheme,
        "-destination",
        destination,
        "-derivedDataPath",
        str(derived_data),
        action,
    ]
    return argv, project, derived_data


def run_xcode_action(
    session: SessionRecord,
    target: str,
    action: str,
    *,
    timeout_s: int = 1800,
) -> CommandResult:
    argv, project, _ = build_xcode_command(session, target, action)
    lint = subprocess.run(
        ["plutil", "-lint", str(project / "project.pbxproj")],
        check=False,
        text=True,
        capture_output=True,
    )
    if lint.returncode:
        return CommandResult(
            f"xcode-{target}-{action}",
            f"Xcode {target} {action}",
            "fail",
            lint.returncode,
            0.0,
            (lint.stdout + lint.stderr)[-16000:],
        )
    started = time.monotonic()
    try:
        result = subprocess.run(argv, check=False, text=True, capture_output=True, timeout=timeout_s)
        status = "pass" if result.returncode == 0 else "fail"
        return CommandResult(
            f"xcode-{target}-{action}",
            f"Xcode {target} {action}",
            status,
            result.returncode,
            time.monotonic() - started,
            (result.stdout + result.stderr)[-32000:],
        )
    except FileNotFoundError:
        return CommandResult(
            f"xcode-{target}-{action}",
            f"Xcode {target} {action}",
            "unavailable",
            None,
            time.monotonic() - started,
            "xcodebuild is unavailable on this host",
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            f"xcode-{target}-{action}",
            f"Xcode {target} {action}",
            "fail",
            None,
            time.monotonic() - started,
            f"xcodebuild timed out after {timeout_s}s: {exc}",
        )


def process_host_request(path: Path) -> Path:
    raw = _read_request(path)
    if set(raw) != {"schema_version", "type", "session_id", "commit_sha", "target", "action"}:
        raise HostActionError("host request has unexpected or missing fields")
    if raw["schema_version"] != 1 or raw["type"] != "xcode":
        raise HostActionError("unsupported host request")
    session = load_session(str(raw["session_id"]))
    current = subprocess.run(
        ["git", "-C", str(session.worktree), "rev-parse", "HEAD"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    if current != raw["commit_sha"]:
        raise HostActionError("host request commit does not match the session worktree")
    result = run_xcode_action(session, str(raw["target"]), str(raw["action"]))
    output = path.parent.parent / "results" / f"{path.stem}.json"
    _write_json_atomic(output, result.__dict__)
    path.unlink()
    return output


def serve_host_actions(*, poll_seconds: float = 0.5) -> None:
    """Serve strict request files for container callers; no arbitrary argv is accepted."""
    while True:
        processed = False
        for session in list_sessions():
            requests = Path(os.environ.get("MSANDBOX_STATE_DIR", Path.home() / ".local/state/matcha-msandbox")) / "sessions" / session.id / "bridge/requests"
            if not requests.is_dir():
                continue
            for request in sorted(requests.glob("*.json")):
                processed = True
                try:
                    process_host_request(request)
                except Exception as exc:
                    error_path = requests.parent / "results" / f"{request.stem}.json"
                    _write_json_atomic(error_path, {"status": "fail", "error": str(exc)})
                    request.unlink(missing_ok=True)
        time.sleep(0.05 if processed else poll_seconds)


def install_host_service(
    *,
    msandbox_bin: Path | None = None,
    launch_agents_dir: Path | None = None,
    load: bool = True,
) -> Path:
    """Install the narrow Xcode bridge as a per-user macOS LaunchAgent."""
    if __import__("sys").platform != "darwin":
        raise HostActionError("the Xcode host service can only be installed on macOS")
    binary = (msandbox_bin or Path.home() / ".local/bin/msandbox").resolve()
    if not binary.is_file():
        raise HostActionError(f"msandbox launcher is missing: {binary}")
    destination_dir = launch_agents_dir or Path.home() / "Library/LaunchAgents"
    destination_dir.mkdir(parents=True, exist_ok=True)
    logs = Path.home() / "Library/Logs/matcha-msandbox"
    logs.mkdir(parents=True, exist_ok=True, mode=0o700)
    template = Path(__file__).parent / "launchd/com.matcha.msandbox-hostd.plist.template"
    rendered = template.read_text(encoding="utf-8").replace(
        "__MSANDBOX_BIN__", str(binary)
    ).replace("__LOG_DIR__", str(logs))
    destination = destination_dir / "com.matcha.msandbox-hostd.plist"
    temporary = destination.with_suffix(".plist.next")
    temporary.write_text(rendered, encoding="utf-8")
    os.replace(temporary, destination)
    if load and shutil.which("launchctl"):
        domain = f"gui/{os.getuid()}"
        subprocess.run(
            ["launchctl", "bootout", f"{domain}/com.matcha.msandbox-hostd"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        result = subprocess.run(
            ["launchctl", "bootstrap", domain, str(destination)],
            check=False,
            text=True,
            capture_output=True,
        )
        if result.returncode:
            raise HostActionError(result.stderr.strip() or "launchctl bootstrap failed")
    return destination
