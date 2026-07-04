// Corporate enforcement headlines. Figures fact-checked against official press releases
// (EEOC/CFPB/OSHA/DOJ/SEC/AG/CRD/DPC) + reputable reporting — keep them defensible.
const HEADLINES = [
  {
    text: "Wells Fargo — $3.7B CFPB penalty for consumer account abuses (2022)",
    tag: "CFPB",
  },
  {
    text: "Activision Blizzard — $54M CA Civil Rights settlement for gender pay bias (2023)",
    tag: "CRD",
  },
  {
    text: "Norfolk Southern — $600M settlement over East Palestine derailment (2024)",
    tag: "SETTLEMENT",
  },
  {
    text: "Tesla — $3.2M jury verdict for racial harassment at Fremont (Diaz, 2023)",
    tag: "VERDICT",
  },
  {
    text: "Boeing — $200M SEC penalty for misleading investors on the 737 MAX (2022)",
    tag: "SEC",
  },
  {
    text: "Goldman Sachs — $215M class-action settlement for gender bias (2023)",
    tag: "CLASS ACTION",
  },
  {
    text: "Dollar General — $12M OSHA settlement over repeated store safety violations (2024)",
    tag: "OSHA",
  },
  {
    text: "Uber + Lyft — $328M NY AG settlement for driver wage deductions (2023)",
    tag: "NY AG",
  },
  {
    text: "Meta — €1.2B EU GDPR fine for unlawful US data transfers (2023)",
    tag: "GDPR",
  },
  {
    text: "Walmart — $14M class-action settlement for pregnancy discrimination (2019)",
    tag: "CLASS ACTION",
  },
  {
    text: "Didion Milling — federal convictions for falsifying OSHA safety logs; 5 died (2023)",
    tag: "DOJ",
  },
  {
    text: "Google — $118M class-action settlement for gender pay bias (2022)",
    tag: "CLASS ACTION",
  },
  {
    text: 'Starbucks — NLRB judge found "egregious and widespread" labor violations (2023)',
    tag: "NLRB",
  },
  {
    text: "FedEx — $240M settlement for driver misclassification (2016, 20 states)",
    tag: "CLASS ACTION",
  },
  {
    text: "Amazon — $5.9M CA penalty for warehouse-quota violations (AB 701, 2024)",
    tag: "AB 701",
  },
  {
    text: "Walmart — $125M EEOC jury verdict for ADA bias (2021; capped at $300k)",
    tag: "EEOC",
  },
  {
    text: "Chipotle — $20M NYC Fair Workweek & sick-leave settlement (2022)",
    tag: "NYC",
  },
  {
    text: "Wells Fargo — $185M in fines + 5,300 fired in fake-accounts scandal (2016)",
    tag: "CFPB",
  },
  {
    text: "Riot Games — $100M settlement for gender discrimination & harassment (2021)",
    tag: "CLASS ACTION",
  },
  {
    text: "Dollar Tree / Family Dollar — $13M+ in OSHA fines as a repeat safety violator",
    tag: "OSHA",
  },
  {
    text: "McDonald's — $26M class-action settlement for CA wage violations (2019)",
    tag: "CLASS ACTION",
  },
  {
    text: "Activision Blizzard — $18M EEOC settlement for sexual harassment (2022)",
    tag: "EEOC",
  },
];

const ITEMS = [...HEADLINES, ...HEADLINES];

export function ComplianceTicker() {
  return (
    <div
      className="fixed left-0 right-0 z-40 w-full overflow-hidden"
      style={{
        top: "64px",
        backgroundColor: "#0F0F0F",
        borderBottom: "1px solid rgba(255,255,255,0.08)",
        height: "40px",
      }}
    >
      <div className="flex items-center h-full">
        <div
          className="shrink-0 flex items-center gap-2 px-5 h-full border-r text-[11px] font-medium uppercase tracking-[0.18em]"
          style={{
            borderColor: "rgba(255,255,255,0.08)",
            color: "rgba(245,242,237,0.55)",
          }}
        >
          <span className="relative inline-flex w-1 h-1">
            <span
              className="absolute inline-flex w-full h-full rounded-full animate-ping"
              style={{ opacity: 0.5 }}
            />
            <span
              className="relative inline-flex rounded-full w-1.5 h-1.5"
              style={{ backgroundColor: "#A3C57D" }}
            />
          </span>
          Live enforcement
        </div>

        <div className="overflow-hidden flex-1">
          <div
            className="flex items-center gap-10 whitespace-nowrap animate-[ticker_120s_linear_infinite]"
            style={{ width: "max-content" }}
          >
            {ITEMS.map((item, i) => (
              <span key={i} className="inline-flex items-center gap-3">
                <span
                  className="text-[10.5px] font-medium uppercase tracking-wider px-2 py-[2px] rounded-sm"
                  style={{
                    color: "rgba(245,242,237,0.7)",
                    border: "1px solid rgba(245,242,237,0.3)",
                  }}
                >
                  {item.tag}
                </span>
                <span className="text-[13px]" style={{ color: "rgba(245,242,237,0.7)" }}>
                  {item.text}
                </span>
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
