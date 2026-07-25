import { ASH, BONE, DISPLAY, LEAF, LINE_D } from "../../home/theme";
import { CONTAINER, EYEBROW, SECTION_Y } from "../../home/layout";
import { Reveal } from "../../home/PageChrome";
import { COVERAGE_BODY, COVERAGE_EYEBROW, COVERAGE_HEADING } from "./data";

// Static — deliberately no live jurisdiction/requirement counts. The catalog
// endpoint (/resources/state-guides) is auth-gated, so this page has no public
// source for a real number, and inventing one is exactly what home/data.ts's
// HERO_PROOF comment warns against. The stack shape itself carries the claim.
const LEVELS: { label: string; w: string; note: string; lit: boolean }[] = [
  { label: "Federal", w: "100%", note: "Baseline", lit: false },
  { label: "State", w: "78%", note: "Overlay", lit: false },
  { label: "County", w: "56%", note: "Overlay", lit: false },
  { label: "City", w: "38%", note: "Governs", lit: true },
];

export function Coverage() {
  return (
    <section className={`${SECTION_Y} border-t`} style={{ borderColor: LINE_D }}>
      <div className={CONTAINER}>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-16 items-center">
          <Reveal>
            <span className={EYEBROW} style={{ color: ASH }}>
              {COVERAGE_EYEBROW}
            </span>
            <h2
              className="mt-4 text-[1.7rem] sm:text-[2.1rem] tracking-[-0.015em]"
              style={{ fontFamily: DISPLAY, fontWeight: 300, lineHeight: 1.2, color: BONE }}
            >
              {COVERAGE_HEADING}
            </h2>
            <p className="mt-5 text-[1rem] sm:text-[1.05rem]" style={{ color: ASH, lineHeight: 1.6 }}>
              {COVERAGE_BODY}
            </p>
          </Reveal>

          <Reveal delayMs={100}>
            <div className="rounded-xl border p-6 sm:p-8" style={{ borderColor: LINE_D }}>
              <div className="flex flex-col gap-4">
                {LEVELS.map((l) => (
                  <div key={l.label} className="flex items-center gap-4">
                    <div
                      className="w-16 shrink-0 text-[10px] font-mk-mono uppercase tracking-wider text-right"
                      style={{ color: l.lit ? BONE : ASH, fontWeight: l.lit ? 600 : 400 }}
                    >
                      {l.label}
                    </div>
                    <div className="relative flex-1 h-7 rounded-sm overflow-hidden" style={{ backgroundColor: "rgba(245,242,237,0.03)" }}>
                      <div
                        className="absolute inset-y-0 left-0 rounded-sm flex items-center px-2.5"
                        style={{
                          width: l.w,
                          border: `1px solid ${l.lit ? "transparent" : LINE_D}`,
                          backgroundColor: l.lit ? LEAF : "transparent",
                        }}
                      >
                        <span
                          className="text-[9px] font-mk-mono uppercase tracking-wider whitespace-nowrap"
                          style={{ color: l.lit ? "#14210B" : ASH }}
                        >
                          {l.note}
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              <p className="mt-6 text-[12px]" style={{ color: ASH }}>
                Resolves to the one rule that governs — county and city ordinances checked before state defaults ship.
              </p>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
