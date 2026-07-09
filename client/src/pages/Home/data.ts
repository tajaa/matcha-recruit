export type Product = {
  n: string;
  name: string;
  subheader?: string;
  nameSize?: string;
  blurb: string;
  to: string;
  accent: string;
};

// 2×2 in spirit (software / people) but presented as a stacked editorial index.
export const PRODUCTS: Product[] = [
  {
    n: "01",
    name: "Full Platform",
    subheader: "Full Risk and Employee Relations Suite",
    blurb:
      "Agentic risk management — safety, compliance, and employee relations on one brain.",
    to: "/matcha-platform",
    accent: "#F5F2ED",
  },
  {
    n: "02",
    name: "Matcha Lite",
    subheader: "Incident Reporting and OSHA Logs",
    blurb:
      "Incident reporting, OSHA 300 logs, and a full HR library. Bundled for small teams.",
    to: "/matcha-lite",
    accent: "#F2C14E",
  },
  {
    n: "03",
    name: "Compliance",
    subheader: "Multi-State Jurisdictional Intelligence",
    blurb:
      "Multi-state regulatory tracking, jurisdiction-aware alerts, and audit-ready records.",
    to: "/matcha-compliance",
    accent: "#E2725B",
  },
  {
    n: "04",
    name: "Consulting",
    blurb:
      "Bespoke HR, governance, and employee-relations counsel. Senior practitioners, in the room.",
    to: "/services",
    accent: "#7FB2C9",
  },
];

// Hero carousel slides. Not 1:1 with PRODUCTS: Matcha Lite gets two slides
// (the incident-reporting flow + its OSHA 300 recordkeeping), both keyed "02"
// and titled "Matcha Lite" with the same subheader — the OSHA facet is part
// of the Matcha Lite bundle, not a separate product, so it shouldn't read as
// one. Routed to /matcha-daily so they read as two facets of one product.
// Order is presentation, not the product numbering: lead with the entry-tier
// product (Matcha Lite, then its OSHA facet), then Compliance, then close on
// the Full Platform as the "and everything above, unified" capstone.
// Consulting is people, not an instrument, and stays text-only in the index below.
export const CAROUSEL_PRODUCTS: Product[] = [
  {
    n: "02",
    name: "Matcha Lite: Incident Reporting Pro",
    blurb:
      "Incident reporting, OSHA 300 logs, and a full HR library. Bundled for small teams.",
    to: "/matcha-lite",
    accent: "#F2C14E",
  },
  {
    n: "02",
    name: "Matcha Lite: 1 Click OSHA Logs Export",
    nameSize: "clamp(1.35rem, 1.85vw, 2.1rem)",
    blurb:
      "Recordable incidents flow straight into your OSHA 300 log, 300A summary, and ITA export.",
    to: "/matcha-lite",
    accent: "#F2C14E",
  },
  PRODUCTS[2], // 03 Compliance
  PRODUCTS[0], // 01 Full Platform
];

export const HOME_JSON_LD = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: "Matcha",
  url: "https://hey-matcha.com/",
  description:
    "Full-service HR — an agentic risk & compliance platform, Matcha Lite for small teams, multi-state compliance tracking, and senior advisory.",
  makesOffer: [
    {
      "@type": "Offer",
      itemOffered: {
        "@type": "Service",
        name: "HR Risk & Compliance Platform",
      },
    },
    {
      "@type": "Offer",
      itemOffered: {
        "@type": "Service",
        name: "Matcha Lite — Incident Reporting & HR Records",
      },
    },
    {
      "@type": "Offer",
      itemOffered: {
        "@type": "Service",
        name: "Compliance — Multi-State Regulatory Tracking",
      },
    },
    {
      "@type": "Offer",
      itemOffered: { "@type": "Service", name: "HR & Compliance Consulting" },
    },
  ],
};
