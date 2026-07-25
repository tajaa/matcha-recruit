import { ENFORCEMENT_ACTIONS } from "../../data/enforcementActions";

// Figures fact-checked against official press releases (EEOC/CFPB/OSHA/DOJ/SEC/
// AG/CRD/DPC) + reputable reporting — see data/enforcementActions.ts, shared
// with the Compliance landing page's Stakes section. Keep them defensible.
const HEADLINES = ENFORCEMENT_ACTIONS.map((a) => ({ text: a.text, tag: a.tag }));

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
