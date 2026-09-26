#!/usr/bin/env python3
"""Fetch explicitly; stage/sign offline in Xcode before the app is signed."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SPEC = json.loads((ROOT / "CodexRuntime/runtime.json").read_text())
CACHE = ROOT / ".build/codex" / SPEC["version"]
ARCHIVE = CACHE / SPEC["asset"]


def verify():
    with ARCHIVE.open("rb") as source:
        digest = hashlib.sha256()
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != SPEC["sha256"]:
        raise SystemExit("Codex archive checksum mismatch; remove it and fetch again.")


def main():
    if sys.argv[1:] == ["fetch"]:
        CACHE.mkdir(parents=True, exist_ok=True)
        if not ARCHIVE.exists():
            url = f'https://github.com/openai/codex/releases/download/rust-v{SPEC["version"]}/{SPEC["asset"]}'
            temporary = ARCHIVE.with_suffix(".download")
            urllib.request.urlretrieve(url, temporary)
            temporary.replace(ARCHIVE)
        verify()
        print(f'Codex {SPEC["version"]} verified: {ARCHIVE}')
        return
    if sys.argv[1:] != ["embed"]:
        raise SystemExit("Usage: codex-runtime.py fetch|embed")
    contents = Path(os.environ["TARGET_BUILD_DIR"]) / os.environ["CONTENTS_FOLDER_PATH"]
    destination = contents / "Helpers"
    resources = contents / "Resources/Codex"
    # Remove only our generated artifacts so an unavailable runtime cannot
    # accidentally leave stale helpers from an earlier build.
    for name in ("codex", "codex-code-mode-host"):
        (destination / name).unlink(missing_ok=True)
    if resources.exists():
        shutil.rmtree(resources)
    if not ARCHIVE.exists():
        message = "Run python3 scripts/codex-runtime.py fetch from platforms/desktop/Espresso to bundle Codex."
        if os.environ.get("CONFIGURATION") == "Debug":
            print("warning: " + message + " Local Codex will be unavailable in this build.")
            return
        raise SystemExit(message)
    if "x86_64" in os.environ.get("ARCHS", ""):
        raise SystemExit("Bundled Codex is arm64-only. Build ARCHS=arm64; Intel research is not validated.")
    verify()
    destination.mkdir(parents=True, exist_ok=True)
    resources.mkdir(parents=True)
    # Research needs only these two helpers. Voice, ripgrep and shell resources
    # are intentionally not distributed; their capabilities are disabled.
    with tarfile.open(ARCHIVE) as archive:
        for name in ("codex", "codex-code-mode-host"):
            member = archive.getmember("bin/" + name)
            if not member.isfile():
                raise SystemExit("Expected a regular Codex executable")
            output = destination / name
            with archive.extractfile(member) as source, output.open("wb") as target:
                shutil.copyfileobj(source, target)
            output.chmod(0o755)
            identity = os.environ.get("EXPANDED_CODE_SIGN_IDENTITY") or "-"
            command = ["/usr/bin/codesign", "--force", "--sign", identity,
                       "--entitlements", str(ROOT / "CodexRuntime/Helper.entitlements")]
            if os.environ.get("ENABLE_HARDENED_RUNTIME") == "YES":
                command += ["--options", "runtime"]
            if identity != "-":
                command += ["--timestamp"]
            subprocess.run(command + [str(output)], check=True)
    for name in ("LICENSE", "NOTICE", "runtime.json"):
        shutil.copy2(ROOT / "CodexRuntime" / name, resources / name)


if __name__ == "__main__":
    main()
