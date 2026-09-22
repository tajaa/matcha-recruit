#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_OUTPUT="$(mktemp -d /private/tmp/espresso-ios-core.XXXXXX)"
# Test artifacts are left in this unique temp directory for failure inspection.
xcrun swiftc -module-cache-path "$TEST_OUTPUT/module-cache" \
  "$PROJECT_ROOT/Espresso/Models/MatchaWork/CommonModels.swift" \
  "$PROJECT_ROOT/Espresso/Models/MatchaWork/ProjectModels.swift" \
  "$PROJECT_ROOT/Espresso/Models/MatchaWork/ProjectTaskModels.swift" \
  "$PROJECT_ROOT/Espresso/Models/MatchaWork/ProjectElementModels.swift" \
  "$PROJECT_ROOT/WerkiOS/Support/MobileProjectRules.swift" \
  "$PROJECT_ROOT/WerkiOSTests/MobileProjectRulesTests.swift" \
  -o "$TEST_OUTPUT/mobile-project-tests"
TZ=America/Los_Angeles "$TEST_OUTPUT/mobile-project-tests"
TZ=Pacific/Auckland "$TEST_OUTPUT/mobile-project-tests"
TZ=UTC "$TEST_OUTPUT/mobile-project-tests"
