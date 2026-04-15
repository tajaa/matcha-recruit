# Matcha macOS — Release & Distribution

This document covers how to produce a signed + notarized build of the Matcha macOS app so your team can install and run it outside of Xcode.

The end-to-end pipeline is wrapped in `desktop/Matcha/release.sh`. For day-to-day dev builds use `desktop/Matcha/run.sh` instead — it builds and launches the unsigned debug app without touching notarization.

---

## One-time setup

Do each of these once, per developer machine that will cut releases.

### 1. Developer ID Application certificate

The release script signs with a **Developer ID Application** certificate from the Apple Developer team `5D6TJVCPBK` (shared with the Ahnimal and HCA apps). Install it on this Mac:

1. Open **Xcode → Settings → Accounts**
2. Sign in with the Apple ID that belongs to team `5D6TJVCPBK`
3. Select the team → **Manage Certificates…** → **+** → **Developer ID Application**
4. Confirm it landed in the login keychain:
   ```bash
   security find-identity -p codesigning -v | grep "Developer ID Application"
   ```
   You should see one line with a hash and the cert name. If not, the cert didn't install — try again from Xcode.

### 2. App Store Connect API key (for notarization)

`xcrun notarytool` authenticates to Apple's notary service. The preferred path is an App Store Connect API key rather than an app-specific password.

1. Visit https://appstoreconnect.apple.com/access/integrations/api
2. Click **Generate API Key** (or **+** if keys already exist)
3. Name it something like `matcha-notary`, give it the **Developer** role
4. Click **Generate**, then **Download API Key** — you only get ONE download
5. Note the **Key ID** on the list row and the **Issuer ID** shown at the top of the page (it's a UUID)
6. Stash the `.p8` somewhere persistent:
   ```bash
   mkdir -p ~/.appstoreconnect
   mv ~/Downloads/AuthKey_*.p8 ~/.appstoreconnect/
   chmod 600 ~/.appstoreconnect/AuthKey_*.p8
   ```

### 3. Shell environment

Add to `~/.zshrc` (or `~/.bashrc`):

```bash
export APPLE_API_KEY_ID=XXXXXXXXXX                                          # 10-char key ID from the portal
export APPLE_API_ISSUER_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx              # UUID at top of the API keys page
export APPLE_API_KEY_PATH=$HOME/.appstoreconnect/AuthKey_XXXXXXXXXX.p8       # path to the .p8 you downloaded
```

`APPLE_TEAM_ID` is **not** required — it defaults to `5D6TJVCPBK` inside `release.sh` (which also matches what's hard-coded in `Matcha.xcodeproj`). Override only if you're building for a different team.

Reload your shell (`source ~/.zshrc`) or open a new terminal.

### 4. Fallback: app-specific password (if you can't use an API key)

If API keys aren't an option, `release.sh` also accepts:

```bash
export APPLE_ID=you@example.com
export APPLE_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx    # from https://account.apple.com → Sign-In and Security → App-Specific Passwords
```

API keys are preferred because they don't expire and don't prompt for MFA.

---

## Project signing config

Already wired into `desktop/Matcha/Matcha.xcodeproj`:

| Setting | Value |
| --- | --- |
| `DEVELOPMENT_TEAM` | `5D6TJVCPBK` |
| `PRODUCT_BUNDLE_IDENTIFIER` | `com.ahnimal.matcha` |
| `CODE_SIGN_STYLE` | `Automatic` |
| `ENABLE_HARDENED_RUNTIME` | `YES` (required for notarization) |

You shouldn't need to edit these for normal releases. If you later want a different bundle ID (e.g. a white-label build), override at release time with `BUNDLE_ID=com.other.name ./release.sh`.

The app's sandbox entitlements live in `desktop/Matcha/Matcha/Matcha.entitlements` and are compatible with Developer ID distribution: app sandbox on, network client on, user-selected files read-only.

---

## Cutting a release

From `desktop/Matcha/`:

```bash
# Signed, notarized, stapled zip → build/release/Matcha.zip
./release.sh

# Same, plus a .dmg also notarized + stapled → build/release/Matcha.dmg
./release.sh --dmg

# Signed but skip Apple notarization (fast local smoke test)
./release.sh --skip-notarize
```

Typical wall time: 30–90s for the archive + export, 1–5 minutes waiting for Apple's notary service. The script waits on notarytool synchronously and fails loud if anything goes wrong.

### What the script does, in order

1. Writes a temporary `ExportOptions.plist` for `developer-id` distribution
2. `xcodebuild ... archive` with overrides:
   `DEVELOPMENT_TEAM`, `CODE_SIGN_IDENTITY="Developer ID Application"`, `ENABLE_HARDENED_RUNTIME=YES`, optional `PRODUCT_BUNDLE_IDENTIFIER`
3. `xcodebuild -exportArchive` → signed `Matcha.app` in `build/release/export/`
4. `codesign --verify --deep --strict` sanity check
5. `ditto -c -k --keepParent` → `Matcha.zip`
6. `xcrun notarytool submit --wait` → uploads to Apple, blocks until accepted/rejected
7. `xcrun stapler staple` → stamps the ticket onto the `.app`
8. Re-zips so the shipped archive contains the notarization ticket (offline-installable)
9. `spctl --assess --type execute` gatekeeper preflight

### Outputs

All artifacts go to `desktop/Matcha/build/release/`:

```
build/release/
├── Matcha.xcarchive          # the archive; safe to delete
├── export/Matcha.app         # signed + stapled .app
├── Matcha.zip                # what you distribute
├── Matcha.dmg                # if --dmg was passed
└── ExportOptions.plist       # generated each run
```

`Matcha.zip` is the normal artifact to share with your team. Staple means it installs and launches offline — a recipient doesn't need network access at first-launch for Gatekeeper to clear it.

---

## Distributing to your team

Pick whichever of these fits your workflow:

- **Shared drive / S3 / GitHub release**: upload the zip, share the link
- **DMG**: `./release.sh --dmg` if you want a drag-to-/Applications window
- **TestFlight**: not covered here — requires different signing (`app-store` method in `ExportOptions.plist`) and uploading via `xcrun altool` or `xcrun notarytool` with `--app-store`. Ask if you want a variant script.

Recipients should unzip and drag `Matcha.app` to `/Applications`. First launch may show the normal "downloaded from the internet" prompt; because the ticket is stapled, Gatekeeper clears it without a network round-trip.

---

## Troubleshooting

### `error: No signing certificate "Developer ID Application" found`
Your login keychain doesn't have the cert. Repeat **One-time setup → step 1**. Confirm with `security find-identity -p codesigning -v`.

### Notarization rejects with "The binary is not signed with a valid Developer ID certificate"
Usually means the cert was issued under a different team than `DEVELOPMENT_TEAM`. Check `security find-identity -p codesigning -v` — if the cert line shows a team ID other than `5D6TJVCPBK`, either log into Xcode with the right Apple ID and issue a new one, or export `APPLE_TEAM_ID` to match the cert you actually have.

### Notarization rejects with "The executable does not have the hardened runtime enabled"
`ENABLE_HARDENED_RUNTIME = YES` is in the pbxproj, but if someone flipped it off, re-add it. The release script also injects this as a build setting override on the command line.

### `notarytool` submission just hangs
Check you can actually reach the service: `xcrun notarytool history --key ... --key-id ... --issuer ...`. If the API key is wrong you'll get a clear auth error. If it's right but still hanging, Apple is occasionally slow — wait it out or retry.

### Bundle ID clash with another app on the team
Override per-run:
```bash
BUNDLE_ID=com.ahnimal.matcha-staging ./release.sh
```

### Need the full log when something fails
The script writes stdout+stderr to a temp file and only prints the failing line on error. It tells you the full path on the last line — `cat` that to see everything.

---

## Bumping the version

Version is driven by `CFBundleShortVersionString` / `CFBundleVersion` keys, which are currently generated from project settings because `GENERATE_INFOPLIST_FILE = YES`. To bump:

- Open `Matcha.xcodeproj` in Xcode → Target → General → Version / Build, or
- Add `MARKETING_VERSION` and `CURRENT_PROJECT_VERSION` build settings to `project.pbxproj` and edit them there

Either way, bump **before** running `./release.sh` or uploads will collide with the previous build number on Apple's side.

---

## File / script index

| Path | Purpose |
| --- | --- |
| `desktop/Matcha/run.sh` | Dev build + launch (unsigned debug) |
| `desktop/Matcha/release.sh` | Archive + sign + notarize + staple + zip/dmg |
| `desktop/Matcha/Matcha.xcodeproj` | Project with team + bundle ID wired in |
| `desktop/Matcha/Matcha/Matcha.entitlements` | Sandbox + network-client entitlements |
| `desktop/RELEASE.md` | This document |
