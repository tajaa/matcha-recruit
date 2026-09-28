#!/usr/bin/env bash
# Capture every main screen from the running app for design review.
#   MATCHA_UI_EMAIL=... MATCHA_UI_PASSWORD=... [MATCHA_UI_WEEKS_BACK=n] ./screens.sh [simulator name]
# Needs the local backend (dev-remote.sh). PNGs land in build/screens/.
set -euo pipefail
cd "$(dirname "$0")"
device="${1:-iPhone 17 Pro}"
out="$PWD/build/screens"
result="$PWD/build/screens.xcresult"
rm -rf "$out" "$result"
mkdir -p "$out"
xcodegen generate >/dev/null
TEST_RUNNER_MATCHA_UI_EMAIL="${MATCHA_UI_EMAIL:-}" \
TEST_RUNNER_MATCHA_UI_PASSWORD="${MATCHA_UI_PASSWORD:-}" \
TEST_RUNNER_MATCHA_UI_WEEKS_BACK="${MATCHA_UI_WEEKS_BACK:-0}" \
xcodebuild -project MatchaSchedule.xcodeproj -scheme MatchaScheduleScreens \
  -destination "platform=iOS Simulator,name=$device" \
  -resultBundlePath "$result" test >/dev/null || true
xcrun xcresulttool export attachments --path "$result" --output-path "$out" >/dev/null
# Name each PNG after its attachment.
python3 - "$out" <<'PY'
import json, os, sys
out = sys.argv[1]
manifest = json.load(open(os.path.join(out, "manifest.json")))
for test in manifest:
    for item in test.get("attachments", []):
        name = item.get("suggestedHumanReadableName", "")
        label = name.split("_")[0] if name else item["exportedFileName"]
        src = os.path.join(out, item["exportedFileName"])
        if os.path.exists(src):
            os.rename(src, os.path.join(out, f"{label}.png"))
PY
ls "$out"
