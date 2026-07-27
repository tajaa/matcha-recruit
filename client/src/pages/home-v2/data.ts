// Copy + structured data for /home-v2. No JSX here — see Compliance/data.ts
// for the convention this follows on the noir side.

export type NavRow = { to: string; label: string; caption: string };
export type NavGroup = { heading: string; rows: NavRow[] };

// Grouped by the job the capability does, not by SKU name — the mega-menu's
// whole reason to exist. Two groups is deliberate: enough to show breadth,
// not enough to make a visitor read a sitemap. Routes point at whichever
// existing /matcha-* page currently sells that capability (there are no
// per-capability pages yet — see the plan's "Follow-ups").
export const PLATFORM_MENU: NavGroup[] = [
  {
    heading: "Report & respond",
    rows: [
      {
        to: "/matcha-lite",
        label: "Incident Reporting",
        caption: "Magic-link intake, OSHA logs, pattern detection.",
      },
      {
        to: "/matcha-platform",
        label: "Employee Relations",
        caption: "Case management for the issues that follow.",
      },
    ],
  },
  {
    heading: "Stay compliant",
    rows: [
      {
        to: "/matcha-compliance",
        label: "Compliance",
        caption: "Multi-state requirements, tracked automatically.",
      },
      {
        to: "/matcha-platform",
        label: "Handbook & Policy",
        caption: "Generated, audited, and kept current.",
      },
    ],
  },
];

export const PLATFORM_MENU_FOOTER = {
  label: "Compare packages",
  to: "/matcha-platform",
};

export const NAV_LINKS = [
  { to: "/matcha-brokers", label: "Brokers" },
  { to: "/services", label: "Consulting" },
  { to: "/resources", label: "Resources" },
];

export const HERO_EYEBROW = "Risk & people, one system";
export const HERO_LINE_1 = "Managing your risk,";
export const HERO_LINE_2 = "before your risk manages you.";
export const HERO_DECK =
  "Incident reporting, employee relations, and compliance in one system.";

// The furniture row under the hairline — three parallel capabilities, not a
// sequence, so no 01/02/03 numbering (that would be decoration, not
// information). Mirrors the mega-menu's own vocabulary on purpose: nav and
// hero should teach the same words.
export const HERO_DOMAINS = [
  "Incident Reporting",
  "Employee Relations",
  "Compliance",
];
// No invented founding date/metric here — see root CLAUDE.md's rule against
// unsupportable marketing claims. A plain right-aligned label is enough to
// balance the row optically (that's EYEBROW_END's whole job).
export const HERO_FOLIO = "One system, not a point solution";

export const HOME_V2_JSON_LD = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: "Matcha",
  url: "https://hey-matcha.com/",
  description:
    "Incident reporting, employee relations, and compliance in one system — managing your risk before your risk manages you.",
};
