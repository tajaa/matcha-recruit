import { Accent, CellLabel, Glows } from "../../components/marketing/kit/Chrome";
import { Reveal } from "../../components/marketing/kit/motion";
import { display, glassPane } from "../../components/marketing/kit/styles";
import { CONTAINER, SECTION_Y } from "./layout";

/** The point, on a pane of frosted glass over matcha + amber glows — the same
 *  glass as the scheduling page's check report. */
export function Manifesto() {
  return (
    <section className={SECTION_Y}>
      <div className={CONTAINER}>
        <Reveal className="relative">
          <Glows green="14% 22%" amber="86% 78%" />
          <div className="relative rounded-[28px] px-6 py-10 sm:px-14 sm:py-16" style={glassPane}>
            <CellLabel n="03">The point</CellLabel>
            <p
              className="mt-10 max-w-[24ch]"
              style={{ ...display, fontSize: "clamp(2rem, 5.5vw, 4.75rem)", lineHeight: 1.02 }}
            >
              We don&rsquo;t ship software and walk away. We take responsibility for the hardest, most <Accent>human</Accent> part of
              your company.
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
