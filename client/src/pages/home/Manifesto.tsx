import { DISPLAY, MATCHA, NOIR } from "./theme";
import { Reveal } from "./PageChrome";

export function Manifesto() {
  return (
    <section
      style={{ backgroundColor: MATCHA, color: NOIR }}
      className="py-24 sm:py-36"
    >
      <div className="max-w-[1400px] mx-auto px-6 sm:px-10 lg:px-16 xl:px-24">
        <Reveal>
          {/* Folio row — same double-hairline motif as the hero masthead, in
              ink, so the inverted section reads as the next spread of the same
              magazine rather than a different site. */}
          <div className="flex items-baseline justify-between pb-3">
            <span className="text-[11px] tracking-[0.3em] font-mono uppercase">
              The point
            </span>
            <span className="text-[11px] tracking-[0.3em] font-mono uppercase tabular-nums">
              02
            </span>
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
