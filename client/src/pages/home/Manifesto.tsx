import { BONE, DISPLAY, NOIR } from "./theme";
import { CONTAINER, EYEBROW, EYEBROW_END, SECTION_Y } from "./layout";
import { Reveal } from "./PageChrome";

export function Manifesto() {
  return (
    <section style={{ backgroundColor: BONE, color: NOIR }} className={SECTION_Y}>
      <div className={CONTAINER}>
        <Reveal>
          {/* Folio row — the double-hairline motif that used to open the hero.
              The hero dropped it to reclaim the fold; it survives here, where
              the inverted spread is the one place the magazine conceit still
              earns its keep. */}
          <div className="flex items-baseline justify-between pb-3">
            <span className={EYEBROW}>The point</span>
            <span className={`${EYEBROW_END} tabular-nums`}>02</span>
          </div>
          <div style={{ height: 1, backgroundColor: "rgba(14,14,12,0.35)" }} />
          <div
            className="mt-[3px]"
            style={{ height: 1, backgroundColor: "rgba(14,14,12,0.16)" }}
          />
          <p
            className="mt-10 tracking-[-0.02em]"
            style={{
              fontFamily: DISPLAY,
              fontWeight: 300,
              lineHeight: 1.04,
              fontSize: "clamp(2rem, 5.5vw, 4.75rem)",
            }}
          >
            We don&rsquo;t ship software and walk away. We take responsibility
            for the hardest, most{" "}
            <span style={{ fontStyle: "italic" }}>human</span> part of your
            company.
          </p>
        </Reveal>
      </div>
    </section>
  );
}
