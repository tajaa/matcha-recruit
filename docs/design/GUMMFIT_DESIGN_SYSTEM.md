# Gummfit Design System

The Gummfit iOS operator app mirrors the Cappe web operator dashboard. Web
values are canonical. The operator theme is dark-only for now.

## Sources

- Web atoms: `client/src/cappe/components/ui.ts`
- Web shell: `client/src/cappe/components/SurfaceShell.tsx`
- Published-site presets: `client/src/cappe/data/cappeThemes.ts`
- iOS tokens: `platforms/ios/Gummfit/Views/Shared/Theme.swift`

## Operator Tokens

| Role | Web token | Hex |
| --- | --- | --- |
| Canvas | `zinc-950` | `#09090B` |
| Surface | `zinc-900` | `#18181B` |
| Raised surface | `zinc-800` | `#27272A` |
| Input border | `zinc-700` | `#3F3F46` |
| Primary text | `zinc-50` | `#FAFAFA` |
| Secondary text | `zinc-300` | `#D4D4D8` |
| Dim text | `zinc-400` | `#A1A1AA` |
| Muted text | `zinc-500` | `#71717A` |
| Accent | `emerald-500` | `#10B981` |
| Accent emphasis | `emerald-400` | `#34D399` |
| Warning | `amber-400` | `#FBBF24` |
| Info | `sky-400` | `#38BDF8` |
| Danger | `red-400` | `#F87171` |

Control radius is 8pt. Card radius is 12pt. Shared spacing follows 4pt steps
from 4 through 32pt.

## Component Parity

| Web | iOS |
| --- | --- |
| `ui.card` | `gummfitCard()` |
| `ui.btnPrimary` | `.buttonStyle(.gummfitPrimary)` |
| `ui.btnGhost` | `.buttonStyle(.gummfitGhost)` |
| `ui.input` | `.textFieldStyle(GummfitTextFieldStyle())` / `.gummfitInput()` |
| `ui.label` | `GummfitFieldLabel` |
| `ui.heading` / `subtitle` / `muted` | `GummfitTypography` and view helpers |
| `badgeFor(status)` | `GummfitStatusPill` |

## Published Themes

`CappePublishedThemeCatalog` mirrors the published-site preset catalog for
read-only iOS summaries and previews. iOS does not write `theme_config`; page
editing and theme editing remain web handoffs. Published-site fonts and exact
CSS rendering remain owned by the web renderer.
