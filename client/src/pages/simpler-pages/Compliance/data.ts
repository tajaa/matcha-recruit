import { COMPLIANCE_CATEGORIES } from "../../home/instruments/ComplianceInstrument";

/**
 * Copy + structured data for the noir /matcha-compliance rebuild. Colours and
 * layout rhythm come from `pages/home/theme.ts` / `pages/home/layout.ts` — this
 * file owns words and lists only.
 */

export const HERO_EYEBROW = "Standalone compliance platform";

// "every rule" LEAF italic, "each" AMBER italic — rendered directly in Hero.tsx
// to match the home hero's inline-accent pattern (home/Hero.tsx:116-117).
export const HERO_HEADLINE_PARTS = {
  lead: "We track ",
  accent1: "every rule",
  mid: " that governs ",
  accent2: "each",
  tail: " of your locations.",
};

export const HERO_DECK =
  "Federal down to city, always current. When it changes, you hear it first.";

export const STAKES_EYEBROW = "The stakes";
export const STAKES_HEADING = "Every row above is a rule someone missed.";
export const STAKES_BRIDGE =
  "This is the surface Matcha watches — the same cascade you just saw resolve, run against your own locations.";
export const STAKES_DISCLAIMER =
  "Public enforcement actions and settlements, cited by agency and year. Not Matcha customers.";

export const ONE_SYSTEM_EYEBROW = "What's inside";
export const ONE_SYSTEM_HEADING = "Four systems, one product.";
export const ONE_SYSTEM_SUB =
  "Jurisdiction tracking, handbook audits, policy management, and credentialing — each stands on its own; together they cover the compliance surface a growing team can't afford to miss.";

export type CapabilityItem = {
  id: string;
  icon: "scale" | "bell" | "file-text" | "library" | "badge-check" | "list-checks";
  title: string;
  caption: string;
};

// Mirrors the old CoverageGrid's six cards, kept — it was the one section that
// named every capability precisely. The two duplicate PillarsGrid rows are gone;
// this is now the only place the six get listed, alongside the live instruments.
export const CAPABILITIES: CapabilityItem[] = [
  {
    id: "jurisdiction",
    icon: "scale",
    title: "Jurisdiction stack",
    caption: "Everything that applies where you operate, in one place and always current.",
  },
  {
    id: "change",
    icon: "bell",
    title: "Change alerts",
    caption: "The law moves before you do — so you hear about it before it becomes a problem.",
  },
  {
    id: "handbook",
    icon: "file-text",
    title: "Handbook audit",
    caption: "See exactly where your handbook falls short of your state, in a report you can hand to counsel.",
  },
  {
    id: "policy",
    icon: "library",
    title: "Policy library",
    caption: "Every policy kept current in one place, so nothing quietly goes out of date.",
  },
  {
    id: "credential",
    icon: "badge-check",
    title: "Credentialing",
    caption: "The right credentials tracked to the date, flagged long before anything lapses.",
  },
  {
    id: "actions",
    icon: "list-checks",
    title: "Owned actions",
    caption: "Every gap becomes someone's job with a due date — nothing sits unresolved.",
  },
];

// Re-exported so OneSystem's legislation-watch callout and the hero instrument
// read from the same list and can't drift.
export { COMPLIANCE_CATEGORIES };

export const COVERAGE_EYEBROW = "Depth, not a checklist";
export const COVERAGE_HEADING = "Federal, state, county, and city — resolved to the one rule that actually governs.";
export const COVERAGE_BODY =
  "Most compliance tools stop at the state line. Ours doesn't: county and city ordinances override state defaults constantly — predictive scheduling, paid sick leave accrual, biometric consent — and missing the local layer is how a compliant-looking company gets fined anyway.";

export const PRICING_EYEBROW = "Pricing";
export const PRICING_HEADING = "One price per employee. No per-jurisdiction surcharge.";
export const PRICING_NOTE = "Billed monthly · exact price confirmed at signup";

export const CLOSING_HEADING = "Start tracking what governs you.";
export const CLOSING_SUB = "Live in minutes. No implementation call required.";

export const COMPLIANCE_JSON_LD = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Service",
      "@id": "https://hey-matcha.com/matcha-compliance#service",
      name: "Matcha Compliance",
      serviceType: "Multi-state employment compliance monitoring",
      url: "https://hey-matcha.com/matcha-compliance",
      provider: { "@type": "Organization", name: "Matcha", url: "https://hey-matcha.com/" },
      areaServed: { "@type": "Country", name: "United States" },
      description:
        "Standalone multi-state employment compliance platform — jurisdiction tracking from federal to city, change alerts, handbook audits, policy management, and credentialing.",
    },
    {
      "@type": "BreadcrumbList",
      itemListElement: [
        { "@type": "ListItem", position: 1, name: "Matcha", item: "https://hey-matcha.com/" },
        { "@type": "ListItem", position: 2, name: "Compliance", item: "https://hey-matcha.com/matcha-compliance" },
      ],
    },
  ],
};
