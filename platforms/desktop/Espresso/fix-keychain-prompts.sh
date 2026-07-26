#!/usr/bin/env zsh
# One-time fix: stop the keychain prompt storm during xcodebuild / codesign /
# Xcode Organizer upload / release-appstore.sh.
#
# Two root causes get fixed in one shot:
#   1. Per-key ACL — codesign/altool/productbuild aren't on the allowed-apps
#      list for your signing private keys, so each invocation prompts.
#      Fix: set-key-partition-list grants apple-tool/apple/codesign access to
#      every sign-capable key in the login keychain.
#   2. Keychain auto-lock — login keychain locks after 5 min idle / on sleep,
#      so the *next* signing op prompts for the keychain password to unlock.
#      Fix: set-keychain-settings with no flags disables both timers.
#
# Run once: ./fix-keychain-prompts.sh
# Re-run after: adding a new signing cert, rotating Apple Distribution, etc.

set -e

KEYCHAIN="$HOME/Library/Keychains/login.keychain-db"

if [[ ! -f "$KEYCHAIN" ]]; then
    echo "error: login keychain not found at $KEYCHAIN" >&2
    exit 1
fi

read -rs "PW?login password: "
echo

echo "==> unlocking keychain"
security unlock-keychain -p "$PW" "$KEYCHAIN"

echo "==> granting codesign/altool/Xcode access to all signing keys"
security set-key-partition-list \
    -S apple-tool:,apple:,codesign:,unsigned: \
    -s \
    -k "$PW" \
    "$KEYCHAIN" >/dev/null

echo "==> disabling keychain auto-lock (no idle timeout, no lock on sleep)"
security set-keychain-settings "$KEYCHAIN"

unset PW

echo
echo "==> signing identities now available:"
security find-identity -p codesigning -v | sed 's/^/  /'

echo
echo "done. xcodebuild, Organizer upload, release-appstore.sh: no more prompts."
echo "re-run this script if you add or rotate signing certs."
