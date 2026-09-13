from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .models import CommandResult, SessionRecord
from .state import data_root


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
