import { CONTAINER, EYEBROW, SECTION_Y } from "../home/layout";
import { CREAM_HI, DISPLAY, INK, INK_SOFT, LINE, SANS } from "./theme";
import { paperSurface } from "./PaperGrain";
import { HeroMockup } from "./HeroMockup";

export function RiskInsightsSection() {
  return (
    <section className="relative w-full" style={{ ...paperSurface(CREAM_HI), borderBottom: `1px solid ${LINE}` }}>
      <div className={`${CONTAINER} ${SECTION_Y}`}>
        <div className="max-w-[46ch]">
          <div className={EYEBROW} style={{ color: INK_SOFT, marginBottom: "1rem" }}>
            Risk insights
          </div>
          <h2
            className="tracking-[-0.02em]"
            style={{ fontFamily: DISPLAY, fontWeight: 300, fontSize: "clamp(1.75rem,3.4vw,2.75rem)", lineHeight: 1.15, color: INK }}
          >
            Your own data, surfaced live.
          </h2>
          <p className="mt-4 text-[16px]" style={{ fontFamily: SANS, lineHeight: 1.65, color: INK_SOFT }}>
            Incident trends by severity, worker-comp posture, location risk — pulled straight from what your
            team already reports, no separate analytics tool required.
          </p>
        </div>

        <div className="mt-10 sm:mt-14">
          <HeroMockup />
        </div>
      </div>
    </section>
  );
}
