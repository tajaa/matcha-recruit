/**
 * Corporate enforcement headlines — figures fact-checked against official press
 * releases (EEOC/CFPB/OSHA/DOJ/SEC/AG/CRD/DPC) + reputable reporting. Keep them
 * defensible: don't edit `text` casually, and cite a real source before adding a
 * row.
 *
 * Shared by `components/landing/ComplianceTicker.tsx` (renders `text` verbatim,
 * all rows, as a scrolling strip) and `pages/simpler-pages/Compliance/Stakes.tsx`
 * (renders the structured fields for `featured` rows only, as a designed
 * section) — one source so the two surfaces can't drift apart.
 */
export type EnforcementAction = {
  id: string;
  org: string;
  amount: string;
  what: string;
  year: number;
  tag: string;
  /** Full pre-composed sentence, for the ticker. */
  text: string;
  /** Shown in the Compliance page's Stakes section (6-8 rows, not all 22). */
  featured?: boolean;
};

export const ENFORCEMENT_ACTIONS: EnforcementAction[] = [
  {
    id: "wells-fargo-cfpb-2022",
    org: "Wells Fargo",
    amount: "$3.7B",
    what: "consumer account abuses",
    year: 2022,
    tag: "CFPB",
    text: "Wells Fargo — $3.7B CFPB penalty for consumer account abuses (2022)",
    featured: true,
  },
  {
    id: "activision-crd-2023",
    org: "Activision Blizzard",
    amount: "$54M",
    what: "gender pay bias",
    year: 2023,
    tag: "CRD",
    text: "Activision Blizzard — $54M CA Civil Rights settlement for gender pay bias (2023)",
    featured: true,
  },
  {
    id: "norfolk-southern-settlement-2024",
    org: "Norfolk Southern",
    amount: "$600M",
    what: "the East Palestine derailment",
    year: 2024,
    tag: "SETTLEMENT",
    text: "Norfolk Southern — $600M settlement over East Palestine derailment (2024)",
  },
  {
    id: "tesla-verdict-2023",
    org: "Tesla",
    amount: "$3.2M",
    what: "racial harassment at Fremont (Diaz)",
    year: 2023,
    tag: "VERDICT",
    text: "Tesla — $3.2M jury verdict for racial harassment at Fremont (Diaz, 2023)",
    featured: true,
  },
  {
    id: "boeing-sec-2022",
    org: "Boeing",
    amount: "$200M",
    what: "misleading investors on the 737 MAX",
    year: 2022,
    tag: "SEC",
    text: "Boeing — $200M SEC penalty for misleading investors on the 737 MAX (2022)",
  },
  {
    id: "goldman-sachs-class-action-2023",
    org: "Goldman Sachs",
    amount: "$215M",
    what: "gender bias",
    year: 2023,
    tag: "CLASS ACTION",
    text: "Goldman Sachs — $215M class-action settlement for gender bias (2023)",
  },
  {
    id: "dollar-general-osha-2024",
    org: "Dollar General",
    amount: "$12M",
    what: "repeated store safety violations",
    year: 2024,
    tag: "OSHA",
    text: "Dollar General — $12M OSHA settlement over repeated store safety violations (2024)",
    featured: true,
  },
  {
    id: "uber-lyft-ny-ag-2023",
    org: "Uber + Lyft",
    amount: "$328M",
    what: "driver wage deductions",
    year: 2023,
    tag: "NY AG",
    text: "Uber + Lyft — $328M NY AG settlement for driver wage deductions (2023)",
    featured: true,
  },
  {
    id: "meta-gdpr-2023",
    org: "Meta",
    amount: "€1.2B",
    what: "unlawful US data transfers",
    year: 2023,
    tag: "GDPR",
    text: "Meta — €1.2B EU GDPR fine for unlawful US data transfers (2023)",
  },
  {
    id: "walmart-pregnancy-class-action-2019",
    org: "Walmart",
    amount: "$14M",
    what: "pregnancy discrimination",
    year: 2019,
    tag: "CLASS ACTION",
    text: "Walmart — $14M class-action settlement for pregnancy discrimination (2019)",
  },
  {
    id: "didion-milling-doj-2023",
    org: "Didion Milling",
    amount: "Federal convictions",
    what: "falsifying OSHA safety logs; 5 died",
    year: 2023,
    tag: "DOJ",
    text: "Didion Milling — federal convictions for falsifying OSHA safety logs; 5 died (2023)",
    featured: true,
  },
  {
    id: "google-pay-bias-2022",
    org: "Google",
    amount: "$118M",
    what: "gender pay bias",
    year: 2022,
    tag: "CLASS ACTION",
    text: "Google — $118M class-action settlement for gender pay bias (2022)",
  },
  {
    id: "starbucks-nlrb-2023",
    org: "Starbucks",
    amount: "NLRB finding",
    what: '"egregious and widespread" labor violations',
    year: 2023,
    tag: "NLRB",
    text: 'Starbucks — NLRB judge found "egregious and widespread" labor violations (2023)',
  },
  {
    id: "fedex-misclassification-2016",
    org: "FedEx",
    amount: "$240M",
    what: "driver misclassification (20 states)",
    year: 2016,
    tag: "CLASS ACTION",
    text: "FedEx — $240M settlement for driver misclassification (2016, 20 states)",
  },
  {
    id: "amazon-ab701-2024",
    org: "Amazon",
    amount: "$5.9M",
    what: "warehouse-quota violations (AB 701)",
    year: 2024,
    tag: "AB 701",
    text: "Amazon — $5.9M CA penalty for warehouse-quota violations (AB 701, 2024)",
  },
  {
    id: "walmart-ada-eeoc-2021",
    org: "Walmart",
    amount: "$125M",
    what: "ADA bias (capped at $300k)",
    year: 2021,
    tag: "EEOC",
    text: "Walmart — $125M EEOC jury verdict for ADA bias (2021; capped at $300k)",
  },
  {
    id: "chipotle-nyc-2022",
    org: "Chipotle",
    amount: "$20M",
    what: "Fair Workweek & sick-leave violations",
    year: 2022,
    tag: "NYC",
    text: "Chipotle — $20M NYC Fair Workweek & sick-leave settlement (2022)",
    featured: true,
  },
  {
    id: "wells-fargo-cfpb-2016",
    org: "Wells Fargo",
    amount: "$185M",
    what: "the fake-accounts scandal; 5,300 fired",
    year: 2016,
    tag: "CFPB",
    text: "Wells Fargo — $185M in fines + 5,300 fired in fake-accounts scandal (2016)",
  },
  {
    id: "riot-games-class-action-2021",
    org: "Riot Games",
    amount: "$100M",
    what: "gender discrimination & harassment",
    year: 2021,
    tag: "CLASS ACTION",
    text: "Riot Games — $100M settlement for gender discrimination & harassment (2021)",
  },
  {
    id: "dollar-tree-osha",
    org: "Dollar Tree / Family Dollar",
    amount: "$13M+",
    what: "repeat OSHA safety violations",
    year: 2024,
    tag: "OSHA",
    text: "Dollar Tree / Family Dollar — $13M+ in OSHA fines as a repeat safety violator",
  },
  {
    id: "mcdonalds-ca-wage-2019",
    org: "McDonald's",
    amount: "$26M",
    what: "CA wage violations",
    year: 2019,
    tag: "CLASS ACTION",
    text: "McDonald's — $26M class-action settlement for CA wage violations (2019)",
  },
  {
    id: "activision-eeoc-2022",
    org: "Activision Blizzard",
    amount: "$18M",
    what: "sexual harassment",
    year: 2022,
    tag: "EEOC",
    text: "Activision Blizzard — $18M EEOC settlement for sexual harassment (2022)",
  },
];

export const FEATURED_ENFORCEMENT: EnforcementAction[] = ENFORCEMENT_ACTIONS.filter(
  (a) => a.featured,
);
