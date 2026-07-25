import { ASH, BONE, DISPLAY, LINE_D } from "../../home/theme";
import { CONTAINER, EYEBROW, SECTION_Y } from "../../home/layout";
import { Reveal } from "../../home/PageChrome";
import { FEATURED_ENFORCEMENT } from "../../../data/enforcementActions";
import { STAKES_BRIDGE, STAKES_DISCLAIMER, STAKES_EYEBROW, STAKES_HEADING } from "./data";

/**
 * The enforcement data used to be a 40px marquee under the nav — the strongest
 * argument on the page, moving too fast to read at your own pace. Promoted
 * here as a real section, immediately after the hero's live monitor, with a
 * bridge line so it argues rather than scares.
 */
export function Stakes() {
  return (
    <section className={SECTION_Y}>
      <div className={CONTAINER}>
        <Reveal>
          <div className="max-w-2xl mb-3">
            <span className={EYEBROW} style={{ color: ASH }}>
              {STAKES_EYEBROW}
            </span>
            <h2
              className="mt-4 text-[1.6rem] sm:text-[2rem] tracking-[-0.015em]"
              style={{ fontFamily: DISPLAY, fontWeight: 300, lineHeight: 1.2, color: BONE }}
            >
              {STAKES_HEADING}
            </h2>
            <p className="mt-4 text-[1rem] sm:text-[1.1rem]" style={{ color: ASH, lineHeight: 1.55 }}>
              {STAKES_BRIDGE}
            </p>
          </div>
        </Reveal>

        <Reveal delayMs={80}>
          <div className="mt-10 border-t" style={{ borderColor: LINE_D }}>
            {FEATURED_ENFORCEMENT.map((item) => (
              <div
                key={item.id}
                className="flex flex-wrap items-baseline gap-x-4 gap-y-1 py-4 border-b"
                style={{ borderColor: LINE_D }}
              >
                <span
                  className="text-[10px] font-mk-mono uppercase tracking-[0.16em] shrink-0 px-2 py-0.5 rounded-sm"
                  style={{ border: `1px solid ${LINE_D}`, color: ASH }}
                >
                  {item.tag} · {item.year}
                </span>
                <span
                  className="tabular-nums"
                  style={{ fontFamily: DISPLAY, fontWeight: 400, fontSize: "1.15rem", color: BONE }}
                >
                  {item.org}
                </span>
                <span style={{ color: ASH }}>
                  — {item.amount} for {item.what}
                </span>
              </div>
            ))}
          </div>
          <p className="mt-5 text-[12px]" style={{ color: ASH }}>
            {STAKES_DISCLAIMER}
          </p>
        </Reveal>
      </div>
    </section>
  );
}
