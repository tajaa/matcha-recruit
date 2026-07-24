#!/usr/bin/env bash
# Guards two CI-portability bugs found in code review 2026-07-24
# (matcha/gha-builds-deploys, moving prod deploy onto GitHub Actions):
#
#   1. update-ec2.sh's CI branch used `[ -n "${CI:-}" ]`, which is true for
#      CI=false (several npm/test harnesses export that). It must strict-match
#      "true" like build-and-push.sh already does, or the two scripts silently
#      disagree on what CI means again.
#   2. build-and-push.sh's landing-build-version counter is a gitignored file
#      that doesn't exist on a fresh runner, so a naive CI path would emit
#      "build 1" and regress the footer marker forever. CI must derive the
#      version from GITHUB_RUN_NUMBER instead, and must NOT touch the counter
#      file (the runner FS is ephemeral — writing it there accomplishes
#      nothing and would mask the bug if anyone later relies on it).
#   3. A tracked path with git mode 160000 (a gitlink) and no matching entry
#      in .gitmodules broke deploy run 30132023532: actions/checkout runs
#      `git submodule foreach --recursive` during auth teardown, which is
#      fatal under persist-credentials:false (the code-review hardening) —
#      it had been failing silently in the post-job step before that. Root
#      cause was docs/references/handbooks/{basecamp,sparksuite}-handbook
#      getting `git clone`d instead of downloaded as plain files.
#
# No test framework: this is bash testing bash. Run:
#   ./scripts/tests/test_ci_guards.sh
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UPDATE_EC2="$REPO_ROOT/scripts/update-ec2.sh"
BUILD_PUSH="$REPO_ROOT/scripts/build-and-push.sh"

PASS=0
FAIL=0

check() {
    local desc="$1" ok="$2"
    if [ "$ok" = "0" ]; then
        echo "PASS: $desc"
        PASS=$((PASS + 1))
    else
        echo "FAIL: $desc"
        FAIL=$((FAIL + 1))
    fi
}

################################################################################
# Case 1 — the exact buggy pattern must be gone from update-ec2.sh
################################################################################
if grep -qE '\[ -n "\$\{CI:-\}" \]' "$UPDATE_EC2"; then
    check "update-ec2.sh no longer uses [ -n \"\${CI:-}\" ] (true for CI=false)" 1
else
    check "update-ec2.sh no longer uses [ -n \"\${CI:-}\" ] (true for CI=false)" 0
fi

################################################################################
# Case 2 — both scripts strict-match CI="true" (same predicate shape, so they
# can't quietly drift apart on what counts as "running in CI" again)
################################################################################
if grep -q '"${CI:-}" = "true"' "$UPDATE_EC2" && grep -q '"${CI:-}" = "true"' "$BUILD_PUSH"; then
    check "update-ec2.sh and build-and-push.sh both strict-match CI=\"true\"" 0
else
    check "update-ec2.sh and build-and-push.sh both strict-match CI=\"true\"" 1
fi

################################################################################
# Cases 3-6 — bump_landing_build_version() behavior.
#
# LANDING_BUILD_VERSION_FILE is `readonly` and derived from the sourced
# script's own path (SCRIPT_DIR), so it can't be overridden via env. Instead
# copy build-and-push.sh into a scratch dir and source it FROM there — SCRIPT_DIR
# then resolves to the scratch dir, so LANDING_BUILD_VERSION_FILE lands in a
# throwaway counter file we control, never the real scripts/.landing-build-version.
#
# Sourcing (not executing) means BASH_SOURCE[0] != $0, so the entry-point guard
# at the bottom of build-and-push.sh skips parse_args/main — no real docker
# build is triggered.
################################################################################
run_build_version_case() {
    local desc="$1" run_number="$2" seed_file_content="$3" expect_version="$4" expect_file_content="$5"

    local tmp; tmp="$(mktemp -d)"
    cp "$BUILD_PUSH" "$tmp/build-and-push.sh"
    if [ -n "$seed_file_content" ]; then
        printf '%s' "$seed_file_content" > "$tmp/.landing-build-version"
    fi

    local out
    out=$(cd "$tmp" && env -u CI -u GITHUB_ACTIONS ${run_number:+GITHUB_RUN_NUMBER="$run_number"} bash -c '
        source ./build-and-push.sh
        bump_landing_build_version
        echo "VERSION=${LANDING_BUILD_VERSION}"
    ' 2>&1)

    local got_version
    got_version=$(printf '%s\n' "$out" | grep -oE 'VERSION=[0-9]+' | tail -1 | cut -d= -f2)

    if [ "$got_version" = "$expect_version" ]; then
        check "$desc (version)" 0
    else
        check "$desc (version, expected $expect_version got '$got_version')" 1
    fi

    if [ -n "$expect_file_content" ]; then
        local got_file="(missing)"
        [ -f "$tmp/.landing-build-version" ] && got_file="$(cat "$tmp/.landing-build-version")"
        if [ "$got_file" = "$expect_file_content" ]; then
            check "$desc (counter file)" 0
        else
            check "$desc (counter file, expected '$expect_file_content' got '$got_file')" 1
        fi
    fi

    rm -rf "$tmp"
}

# 3. CI path: GITHUB_RUN_NUMBER=7 -> 7 + CI_BUILD_VERSION_OFFSET (500) = 507
run_build_version_case "CI path derives version from GITHUB_RUN_NUMBER + offset" "7" "" "507" ""

# 4. CI path must not write the counter file (ephemeral runner FS)
run_build_version_case "CI path does not create/touch the counter file" "7" "" "507" ""
tmp_check_dir="$(mktemp -d)"
cp "$BUILD_PUSH" "$tmp_check_dir/build-and-push.sh"
(cd "$tmp_check_dir" && env -u CI -u GITHUB_ACTIONS GITHUB_RUN_NUMBER=7 bash -c '
    source ./build-and-push.sh
    bump_landing_build_version
' >/dev/null 2>&1)
if [ -f "$tmp_check_dir/.landing-build-version" ]; then
    check "CI path leaves no counter file on disk" 1
else
    check "CI path leaves no counter file on disk" 0
fi
rm -rf "$tmp_check_dir"

# 5. Laptop path (no GITHUB_RUN_NUMBER): increments existing counter, writes it back
run_build_version_case "laptop path increments existing counter (480 -> 481)" "" "480" "481" "481"

# 6. Laptop path: garbage counter value resets to 1 (existing validation, unregressed)
run_build_version_case "laptop path resets garbage counter value to 1" "" "abc" "1" "1"

################################################################################
# Case 7 — no gitlink (git mode 160000) may exist without a .gitmodules entry
# that resolves it. `git submodule foreach` (which actions/checkout runs
# during auth teardown) fails immediately on any unresolvable gitlink, and
# under persist-credentials:false that failure is fatal, not a swallowed
# post-step annotation.
################################################################################
gitlink_paths="$(cd "$REPO_ROOT" && git ls-files -s | awk '$1 == "160000" { print $4 }')"

if [ -z "$gitlink_paths" ]; then
    check "no unresolvable gitlinks in the index (no 160000 entries at all)" 0
else
    gitmodules_file="$REPO_ROOT/.gitmodules"
    all_resolved=0
    if [ -f "$gitmodules_file" ]; then
        all_resolved=1
        while IFS= read -r p; do
            [ -z "$p" ] && continue
            grep -qF "path = $p" "$gitmodules_file" || all_resolved=0
        done <<< "$gitlink_paths"
    fi
    if [ "$all_resolved" = "1" ]; then
        check "all gitlinks resolve via .gitmodules" 0
    else
        check "all gitlinks resolve via .gitmodules (found: $(echo "$gitlink_paths" | tr '\n' ' '))" 1
    fi
fi
echo
echo "----------------------------------------"
echo "PASS: $PASS  FAIL: $FAIL"
if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
