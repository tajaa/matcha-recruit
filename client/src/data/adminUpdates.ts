// Product changelog shown at /admin/updates. Newest first. Add an entry here
// whenever a notable feature ships — this is the admin's "what's new + how to
// use it" reference so nothing gets lost after it's built.
//
// `setup` = operator prerequisites before the feature actually works in prod
// (env vars, migrations, third-party config). `tag` flags whether it's live or
// still needs that setup.

export type AdminUpdateTag = 'new' | 'action-needed'

export type AdminUpdate = {
  id: string
  date: string // ISO YYYY-MM-DD
  category: string // product area, e.g. 'Cappe'
  title: string
  summary: string
  whatsNew: string[] // what changed / what you can now do
  howToUse: string[] // user-facing steps in the app
  setup?: string[] // operator prerequisites before it works (optional)
  tag?: AdminUpdateTag
}

export const ADMIN_UPDATES: AdminUpdate[] = [
  {
    id: 'werk-ios-chat',
    date: '2026-06-19',
    category: 'Werk',
    title: 'Native iOS Werk app — chat (channels, DMs, calls) + push',
    summary:
      'A native iOS Werk client now exists, sharing the macOS app’s networking/model/chat core so it stays in lockstep. v1 is the full chat system: real-time channels, direct messages, and LiveKit audio calls / video broadcasts, with APNs push. To test it, flip a business to Werk Lite in Business Features and log into the iOS build as one of its users.',
    whatsNew: [
      'New iOS app target (WerkiOS) inside the existing Xcode project; reuses the same login, channels socket, models, and the channel chat view-model the macOS app uses (no second codebase to keep in sync).',
      'Channels: real-time chat with optimistic send, reactions, replies, edit/delete, typing indicators, presence, and photo attachments.',
      'Direct messages: inbox + thread + start-new-conversation (people search).',
      'Calls & broadcast: join an audio call or watch a live video broadcast from the phone; join is open to channel members, starting one is Pro-gated (same as macOS).',
      'Push (APNs): the phone gets notified of new channel messages, DMs, mentions, and call invites — only when you don’t have the app open (so it never double-buzzes while you’re active on desktop). Tapping a push deep-links to the channel/DM.',
      'Admin: "Werk Lite" is now a per-company toggle in Business Features (previously only set by signup), so you can switch an existing business on for testing.',
    ],
    howToUse: [
      'Admin → Business Features → find the company → turn ON "Werk Lite" AND "Matcha Work" (Werk Lite needs both). Optionally turn on "Werk Lite — any member can start calls".',
      'Build the WerkiOS scheme in Xcode (desktop/Werk/Matcha.xcodeproj) onto a simulator or device.',
      'Log into the app as a business admin or employee of that company — channels and DMs work immediately.',
    ],
    setup: [
      'DB: migration devicetok01 (device_tokens) is applied on dev; apply to prod with ./scripts/migrate-prod.sh (now uses `alembic upgrade heads`).',
      'Push (optional — chat works without it): `pip install aioapns` in the server venv and set APNS_KEY_ID / APNS_TEAM_ID / APNS_AUTH_KEY_PATH / APNS_BUNDLE_ID (com.matchawork.app) / APNS_USE_SANDBOX. Unset → push is a silent no-op.',
      'Real-device push also needs the iOS Push Notifications capability + a signing team on the WerkiOS target. Simulator builds and in-app realtime work without it.',
    ],
    tag: 'action-needed',
  },
  {
    id: 'cappe-freeform-canvas',
    date: '2026-06-19',
    category: 'Cappe',
    title: 'Freeform canvas — click & place individual elements',
    summary:
      'Pro/Business can edit individual elements freely: start from a template and hit "Customize freely" to turn any Hero/CTA/Split/Text section into a draggable freeform layout, or add a "Blank / Freeform" section from scratch. Click any heading, text, image, or button and drag it on a snap-grid — separate desktop & mobile layouts. Squarespace "Fluid Engine"–style.',
    whatsNew: [
      '"Customize freely" on a Hero/CTA/Split/Text section → converts it (keeping its content) into a freeform layout where every piece — heading, subheader, buttons, image — is individually editable. (One-way.)',
      'Or add a "Blank / Freeform" section and drop in heading / text / image / button elements.',
      'Click an element to select it; drag to move (snaps to a grid), drag a corner to resize, double-click text/buttons to retype.',
      'Per-element styling: font/size/weight/spacing/color/align for text; fit/radius for images; label/link/variant/colors/radius for buttons.',
      'Separate Desktop and Mobile layouts — flip the toggle to arrange the phone view independently (auto-stacks until you customize it).',
      'Published pages stay fast: positions render as plain CSS grid (no editor code shipped), so it scales to many sites.',
    ],
    howToUse: [
      'Open a site → a page → the editor opens in Canvas mode (Pro/Business).',
      'On an existing section: select it → "✨ Customize freely" → its content becomes editable elements.',
      'Or Add block → "Blank / Freeform" to build from scratch.',
      'Click an element to edit it in the floating panel; drag to move, corner-drag to resize. Use the Desktop / Mobile toggle to tune each breakpoint, then Save.',
    ],
    tag: 'new',
  },
  {
    id: 'cappe-staff-csv-import',
    date: '2026-06-19',
    category: 'Cappe',
    title: 'Staff CSV import with branch auto-mapping',
    summary:
      'Multi-location businesses can import their team from a CSV. A branch column maps each employee to the right location automatically — no manual re-tagging.',
    whatsNew: [
      'Import staff from a CSV (name required; optional branch, bio, active).',
      'The branch column is matched to a location by name, so each employee auto-lands at their branch; blank = works at all locations.',
      'Re-importing the same name updates that person (branch/bio) instead of creating a duplicate; unknown branch names are reported per-row.',
      'Single-location sites get a simpler template with no branch column.',
    ],
    howToUse: [
      'Open a site → Bookings → Staff → Import CSV.',
      'Download the template (multi-location templates are pre-filled with your real branch names).',
      'Fill in your team, upload, and review the per-row summary (added / updated / branch-mapped / skipped).',
    ],
    tag: 'new',
  },
  {
    id: 'cappe-domains',
    date: '2026-06-18',
    category: 'Cappe',
    title: 'Domain buying, connecting & management',
    summary:
      "Tenants can buy a domain through Cappe (we register it via Porkbun and resell at wholesale + a flat markup), or connect one they already own. Includes an in-app DNS editor, auto-renew, and transfer-out.",
    whatsNew: [
      'Search + buy a domain in the site editor — paid via Stripe on our platform account (we keep the margin).',
      'Connect a domain you already own, verified by a DNS TXT record before it goes live (prevents domain hijacking).',
      'In-app DNS records editor (A / CNAME / MX / TXT…) for domains bought through us.',
      'Auto-renew: the card is saved at purchase; a cron charges the tenant before expiry and only then renews — you never pre-pay for a non-payer.',
      'Transfer-out request flow with the 60-day ICANN lock enforced.',
    ],
    howToUse: [
      'Open a site → Settings → Custom domain.',
      "Type a name to search, pick an available one, and click Buy — the tenant completes Stripe checkout and the domain auto-registers + points at the site.",
      "Or paste a domain they own under “Connect it”, add the shown TXT record at their registrar, and click Verify.",
      'On an active bought domain: use DNS to manage records, toggle Auto-renew, or request Transfer out.',
    ],
    setup: [
      'Apply migrations zzzzcappe19 + zzzzcappe20 (dev → prod).',
      'Fund a Porkbun account, enable API, set PORKBUN_API_KEY / PORKBUN_SECRET_KEY + CAPPE_DOMAIN_MARKUP_CENTS.',
      'Add a Stripe PLATFORM webhook → /api/cappe/domains/webhook, set CAPPE_PLATFORM_WEBHOOK_SECRET.',
      'Stand up Caddy on-demand TLS gated by /api/cappe/tls/authorize (custom domains need their own certs).',
      "Enable the renewal cron: scheduler_settings row task_key='cappe_domain_renewals'.",
      'Full detail in server/app/cappe/DOMAINS.md.',
    ],
    tag: 'action-needed',
  },
  {
    id: 'cappe-storefront',
    date: '2026-06-16',
    category: 'Cappe',
    title: 'Storefront payments, receipts & inventory',
    summary:
      'Each business connects its own Stripe account to take card payments on its Cappe storefront (we take a 2% platform fee). Plus branded receipts and per-variant inventory.',
    whatsNew: [
      'Stripe Connect: customers pay the business directly; a 2% fee routes to the platform.',
      'Receipts: numbered, tax-aware, branded PDF emailed to the customer + downloadable by the owner.',
      'Inventory: per-variant stock, low-stock alerts, manual adjustments with an audit log.',
    ],
    howToUse: [
      'Site → Orders → connect the business Stripe account (one-time onboarding).',
      'Set tax rate + receipt prefix in Shop settings.',
      'Add stock numbers / low-stock thresholds per product or variant; use Adjust to restock or correct.',
    ],
    tag: 'new',
  },
  {
    id: 'cappe-setup-wizard',
    date: '2026-06-15',
    category: 'Cappe',
    title: 'Guided setup wizard + canvas editor for Pro',
    summary:
      'New signups get a short setup wizard (single vs. multi-location), and the free-form canvas editor is now unlocked for Pro.',
    whatsNew: [
      'Post-signup wizard: pick one location or several — shapes CSV imports, bookings, and services.',
      'Canvas (free-form drag editor) is now available on Pro, not just Business.',
    ],
    howToUse: [
      'New tenants land on the wizard automatically on first sign-in.',
      'Pro tenants: open a page → toggle to Canvas mode to drag blocks freely.',
    ],
    tag: 'new',
  },
]
