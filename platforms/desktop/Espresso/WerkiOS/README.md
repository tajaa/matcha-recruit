# Espresso for iOS

The native `WerkiOS` target in `../Matcha.xcodeproj` shares Espresso's models,
networking, task realtime, chat, and AI streaming. The product display name is
Espresso; the existing bundle identifier and scheme remain unchanged.

## Mobile scope

- Solo (`general`, including legacy unspecified type) and collaborative projects.
- Create/name/icon, search, per-user pins, archive/restore, and accept/decline invitations.
- Phone-first grouped task list, search/assigned-to-me filter, earlier completed
  tasks, create/edit/delete, priority, assignee, date, current-round checklist,
  review approval/changes requested, attachments, and activity updates.
- Editable notes with inline Markdown preview, draft protection, delete confirmation,
  and a best-effort remote-change check before saving.
- Files and media together: document import (20 MB mobile limit), in-app web
  preview/share, folders, moving files, and confirmed deletion.
- Owner-managed collaborator invitations/removal; read-only roles remain read-only.
- Project AI conversations, existing collaborative channel chat, direct messages,
  calls, broadcasts, and APNs navigation.
- Native Liquid Glass controls on iOS 26, frosted content cards, diffused neutral
  backgrounds and restrained champagne/sage accents. Older iOS versions use
  system-material fallbacks. Includes dark appearance, Dynamic Type, VoiceOver
  labels, tablet-width layouts, opaque Reduce Transparency/Increase Contrast
  surfaces, and Reduce Motion-aware press feedback.
- Current entitlements, sign-out token cleanup, and configuration-specific APNs environment.

Specialist project types (presentations/blog/recruiting), Elements/Props, AutoPR
controls, full historical review rounds, note revision approval, offline editing,
cross-project personal dashboard, and project permanent deletion remain desktop
workflows. Archiving is the reversible mobile project-removal action. Notes do
not have a server-side compare-and-swap revision API: the preflight conflict
check narrows, but cannot eliminate, concurrent-edit races.

## Build and checks

From the repository root:

```sh
ruby platforms/desktop/Espresso/scripts/add_ios_target.rb
./scripts/xcode-build.sh espresso-ios build
./scripts/xcode-build.sh espresso-ios test
```

The generator preserves target identity, build number, signing configuration,
package dependencies and the existing scheme. New iOS Swift files/resources are
registered automatically. Tests live outside `WerkiOS/` so they never join the app.
`test` runs host-side model/rule checks in Los Angeles, Auckland and UTC; it is
not a UI/device test suite. PR CI builds the mobile target and runs these checks.

For an unsigned isolated build with cached packages:

```sh
xcodebuild -project platforms/desktop/Espresso/Matcha.xcodeproj \
  -target WerkiOS -configuration Debug -sdk iphonesimulator \
  -clonedSourcePackagesDirPath /private/tmp/espresso-ios-packages \
  -skipPackageUpdates SYMROOT=/private/tmp/espresso-ios-direct \
  CODE_SIGNING_ALLOWED=NO build
```

The local Xcode 26.5 SDK could compile/link both simulator architectures via the
direct target even though scheme destination resolution reported a missing iOS
platform. The available 26.1 simulator ran the isolated screens successfully.
After asset bundling, `actool` requires the matching 26.5 simulator runtime;
install the matching iOS platform/runtime in Xcode Settings → Components to
complete the resource-inclusive build on that machine.

For source-only simulator validation on that machine, append
`EXCLUDED_SOURCE_FILE_NAMES=Assets.xcassets` to the unsigned build command.
This compiles/links the app but omits the icon and brand catalog; do not use it
for distribution or to validate bundled artwork. The full final source set
also passed `swiftc -typecheck` against the 26.5 simulator SDK.

## Safe visual QA

Debug builds accept `-espresso-preview` with optional `-project`, `-login`,
`-dark`, `-large`, `-opaque`, `-contrast`, and `-reduce-motion`. This renders the actual views with static sample data,
skips session restoration/network loads, and disables interaction. The fixture
entry point and sample data are compiled out of Release. Never use screenshots
of this mode as evidence of live-backend functionality.

The accessibility flags exercise Espresso's custom surfaces and press style;
system bars and controls require the corresponding iOS accessibility settings.
On iOS 17–18, control surfaces use regular system material rather than Liquid
Glass. The new APIs are guarded at both compiler and OS availability boundaries.

## Release checklist

- Set the signing team/provisioning for existing `com.matchawork.app`.
- Verify the icon is an opaque 1024×1024 image before App Store submission.
  The catalog currently copies the existing desktop icon (with alpha). A new
  opaque rendition is bundled as `BrandMark`; it needs an approved mechanical
  resize from 1254×1254 before replacing the AppIcon source.
- Run a signed physical-device pass for login/restore/sign-out, two-account
  isolation, invitations, each write flow, upload failure recovery, and reconnect.
- Test APNs production delivery and task links; test microphone/camera/calls
  while backgrounding. Release entitlements select `production`, Debug selects
  `development`; the provisioning profile must agree.
- Test iPad, smaller phones and all accessibility text sizes interactively.
- Exercise API errors, quota/plan errors, collaborator access revocation and
  concurrent edits against a disposable dev account. No live-backend writes or
  invitations were sent while implementing this change.
- Offline data editing/queueing is not implemented; drafts are view-local.

## Artwork provenance

`Resources/Assets.xcassets/BrandMark.imageset/espresso-ios.png` was generated with
the built-in image-generation tool using the existing desktop icon as an edit
target. The original desktop asset is unchanged. Final prompt:

> Preserve the sculptural ivory lowercase e with its copper inner faces, its
> proportions, position, lighting and espresso-brown palette. Change only the
> background: extend the same dark espresso-brown surface to fill the entire
> square, edge to edge. No transparent pixels, no alpha channel, no pre-rounded
> corners, no outer black margin or inset tile border. iOS will mask the square.
> Keep the e mark identical to the reference. No extra text, graphics, or watermark.

Requested output was 1024×1024 opaque RGB PNG; received 1254×1254 opaque PNG.
