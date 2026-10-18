# Gummfit iOS — native Liquid Glass refresh

Status: proposed implementation plan. Updated October 10, 2026.

## Direction

Make Gummfit feel at home on current iOS: adaptive light and dark appearance,
native Liquid Glass navigation and controls, emerald accents, and clear content
hierarchy. The user's final preference is **whichever feels most iOS native**;
this supersedes the earlier choice of bold glass throughout.

Glass should be most apparent in the tab bar, toolbar actions, site switcher,
editor controls, and message composer. Orders, earnings, messages, form fields,
and other dense content need stable, readable surfaces. Let content extend
beneath system chrome where appropriate so the material has something to reveal.

Use native SwiftUI previews and simulator captures to settle material strength,
spacing, and motion. A browser mockup cannot validate Apple's actual rendering.

## What is already in the app

All paths below are relative to `platforms/ios/Gummfit/` unless stated otherwise.

- `Views/Shared/Theme.swift` centralizes colors, cards, list styling, and navigation
  chrome. Its palette is fixed to dark zinc/emerald, and
  `gummfitScreenChrome()` forces an opaque navigation background and dark toolbar.
- `Views/Shared/GummfitButtonStyle.swift` implements custom filled, secondary,
  ghost, and destructive buttons. `GummfitInputStyle.swift` similarly paints
  custom input backgrounds and borders.
- `Views/Owner/OwnerTabView.swift` and `Views/Creator/CreatorTabView.swift` already
  use native `TabView` navigation. Both force dark appearance; `LoginView.swift`
  also forces dark appearance.
- `Views/Owner/HomeView.swift` and `Views/Creator/CreatorDashboardView.swift` use
  multiple nested cards and metric tiles. They are good first screens for
  establishing the new hierarchy.
- `Views/Owner/Editor/PageEditorView.swift` has a floating capsule using
  `.ultraThinMaterial`; it does not yet use native Liquid Glass. The preview
  extends to the bottom beneath the overlaid controls.
- `Views/Owner/Sales/SalesRootView.swift` paints an opaque surface behind its
  segmented picker. `Views/Owner/Inbox/ThreadDetailView.swift` uses a separate
  bottom reply row that should be assessed with keyboard and safe-area behavior.
- `Tests/GummfitThemeTests.swift` locks several current color and radius values.
  These assertions will need to reflect intentional design changes.
- The deployment target is iOS 17.0. Local Xcode reports 26.6 with iOS 26.5 SDKs.
  `project.yml` still declares Xcode 15.0 metadata; this does not identify the
  compiler actually being used. The generated Xcode project is tracked.

## Visual specification

| Surface | Planned treatment |
|---|---|
| App canvas | Semantic system backgrounds that follow device appearance; restrained emerald accents |
| Main navigation | System tab bar and navigation bar, with automatic material and scroll-edge behavior |
| Primary action | Native prominent glass where appropriate on iOS 26+, emerald tint, clear disabled/loading states |
| Secondary actions | Native glass or standard toolbar buttons according to placement |
| Dashboard | Larger section headings, fewer nested containers, grouped readable metrics, generous spacing |
| Editor dock | Native glass action group over the site preview, with safe-area-aware positioning |
| Lists and forms | Native grouped surfaces, standard pickers and fields, semantic separators and labels |
| Messaging | Readable message bubbles and a glass composer surround with a stable input surface |
| Sheets and menus | System presentation, standard dismissal and action placement, detents only where useful |
| Motion | System transitions and interaction feedback; custom morphing only for a real state change |

Retain SF Symbols, Dynamic Type, and the existing owner/creator destinations.
Destructive actions retain their semantic roles and confirmation behavior.
Published-site themes remain controlled by each site's own design settings;
the operator app's appearance must not recolor the website preview.

## Implementation sequence

### 1. Establish a native baseline and shared appearance

1. Capture the current owner Home, creator Home, editor, sales list, login, and
   a representative form on the installed simulator. Include loading, empty,
   and error states for representative screens.
2. Inventory all consumers of shared theme, button, input, card, and chrome
   helpers before changing them. Inspect call sites beyond the initial screens.
3. Introduce semantic colors for canvas, grouped content, labels, separators,
   accent, and statuses. Define light, dark, and increased-contrast variants
   where custom brand colors are needed.
4. Remove forced dark appearance as part of the same change that makes every
   affected screen legible in light mode. Centralize the appearance policy.
5. Let native navigation determine its material on iOS 26+. Preserve a coherent
   older-OS treatment through availability checks in shared helpers.
6. Keep iOS 17 support. Gate each new API at its actual availability; reconcile
   `project.yml` metadata and regenerate the tracked project when appropriate.

Deliverable: a shared foundation that renders legibly in both appearances,
with screenshots from representative screens before broader restyling.

### 2. Refresh the navigation and dashboards

1. Keep both native tab shells and their existing destinations, selection,
   unread badge, site-switch identity, and scene lifecycle behavior.
2. Remove opaque styling that prevents system bar materials from showing.
   Keep normal system tab behavior initially; evaluate scroll minimization only
   after checking navigation discoverability and accessibility.
3. Refine owner Home into a clear site identity, attention section, metrics,
   and quick actions. Reduce nested card borders and retain useful status labels.
4. Apply the same visual hierarchy to creator Home, with profile identity,
   offers, active deals, and earnings remaining easy to scan.
5. Use native toolbar menus for site switching and related actions. Allow long
   site names, large text, and compact widths to reflow.

Deliverable: owner and creator Home become the reference screens for the app.

### 3. Update the editor and messaging controls

1. Replace the editor's material capsule with a native Liquid Glass control
   group on iOS 26+, using `GlassEffectContainer` for custom grouped effects.
2. Prefer `.buttonStyle(.glass)` and `.glassProminent` for buttons; reserve
   `.glassEffect` for custom control surfaces that need it. Avoid layering a
   second glass background onto controls already rendered by the system.
3. Position the editor dock with safe-area-aware layout. Verify that the last
   section of the website remains reachable and selectable beneath it.
4. Preserve Save, undo/redo, dirty-state handling, selection, and the Sections,
   Theme, and Merlin sheets. Use morphing only when a control genuinely expands
   or changes state; Reduce Motion gets a simpler transition.
5. Apply the same control treatment to Inbox and Merlin composers. Exercise the
   keyboard, multiline text, send progress, disabled actions, and error banners.

Deliverable: native glass feels useful during editing and conversation, with
working content and controls remaining visible at all supported text sizes.

### 4. Carry the system through the remaining screens

Roll out shared components across Catalog, Sales/Bookings, Inbox, More/settings,
creator Profile/Deals/Earnings, authentication, and setup flows. Inventory the
remaining views so no hardcoded dark text/background pairing is missed.

Use native grouped lists, forms, pickers, menus, and sheets where they fit.
Make destructive, loading, unavailable, selected, and validation states
consistent. Preserve existing feature gates, web handoffs, and action behavior.
Keep the work focused on the native presentation layer and its UI tests.

Deliverable: a complete appearance pass across owner, creator, and signed-out
experiences, including all modal presentations.

### 5. Validate and prepare the release

Run the build and tests below, then validate visually on iPhone and iPad.
Compare both appearances, normal and accessibility text sizes, VoiceOver,
Increase Contrast, Reduce Transparency, Reduce Motion, and available system
Liquid Glass appearance settings. Custom surfaces must respect these settings.

Exercise the existing README smoke paths for owner site creation/publishing,
catalog and order handling, marketing, creator setup, and collaboration. Add
focused UI regression coverage for tab selection, site switching, editor dock
layout, and keyboard/composer behavior when those surfaces change.

Profile long lists, dashboard scrolling, editor preview, and keyboard
transitions on a physical supported device. Investigate regressions against the
baseline; avoid per-row glass effects and continuous decorative animations.

Deliverable: visual comparison captures, build/test results, recorded device
coverage, and a release candidate ready for the existing release process.

## Build and validation commands for implementation

From `platforms/ios/Gummfit/`, with an available named simulator:

```sh
xcrun simctl list devices available
make generate
make build SIM="iPhone 17 Pro"
make test SIM="iPhone 17 Pro"
```

Replace the example device name with one returned by the inventory. XcodeGen
must be installed before generation. Regenerate and inspect the tracked project
diff when the source inventory or project configuration changes.

Also exercise the repository CI build path after project generation, from the
repository root, using an available destination:

```sh
XCODE_DESTINATION='platform=iOS Simulator,name=iPhone 17 Pro' ./scripts/xcode-build.sh gummfit build
git diff --check
```

Validate an older supported OS separately from the iOS 26+ run. If its runtime
or physical device is unavailable, record that coverage gap explicitly. A
deployment-target compile alone does not verify the fallback's appearance.

Existing theme tests should retain meaningful palette/semantic guarantees while
allowing the approved geometry changes. Screenshot or UI checks should validate
appearance and interaction, rather than merely repeat token constants.

## Completion criteria

- Device appearance controls the entire operator app, including login and sheets.
- Native glass is clearly visible in navigation and high-value controls on iOS 26+.
- Older supported OS versions remain readable and functional.
- Text, statuses, and actions remain legible over varied content and website themes.
- No content or action is obscured by the tab bar, editor dock, keyboard, or sheets.
- Existing owner, creator, editor, and messaging workflows retain their behavior.
- Required builds/tests pass; any device or infrastructure gaps are documented.

## Evidence and references

This planning pass inspected the current SwiftUI theme, shared controls, tab
shells, dashboards, editor, representative sales/messaging views, project
configuration, theme tests, Makefile, and repository build wiring. It verified
the installed Xcode/SDK versions. App builds, tests, simulator captures, and
device profiling are implementation gates and have not been run for this plan.

Apple's guidance supports using standard navigation and controls, reducing
custom background overrides, and testing accessibility settings:
[Adopting Liquid Glass](https://developer.apple.com/documentation/technologyoverviews/adopting-liquid-glass).

The custom-effects APIs provide glass surfaces and coordinated group transitions:
[Applying Liquid Glass to custom views](https://developer.apple.com/documentation/swiftui/applying-liquid-glass-to-custom-views).
