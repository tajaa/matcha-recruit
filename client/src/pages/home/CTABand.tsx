import { ASH, BONE, DISPLAY, LEAF, NOIR } from "./theme";
import { CONTAINER, SECTION_Y_LG } from "./layout";
import { Reveal } from "./PageChrome";

export function CTABand({ onDemoClick }: { onDemoClick: () => void }) {
  return (
    <section className={SECTION_Y_LG}>
      <Reveal className={`${CONTAINER} text-center`}>
        <h2
          className="tracking-[-0.02em]"
          style={{
            fontFamily: DISPLAY,
            fontWeight: 300,
            lineHeight: 0.92,
            fontSize: "clamp(2.75rem, 9vw, 8rem)",
          }}
        >
          Find your{" "}
          {/* Was `color: MATCHA` — an alias for BONE, so the closing CTA's
              emphasis rendered as plain body colour. LEAF is the accent the
              markup was reaching for, and it matches the hero's "people". */}
          <span style={{ color: LEAF, fontStyle: "italic" }}>
            starting line.
          </span>
        </h2>
        <p
          className="mt-7 mx-auto max-w-lg text-lg"
          style={{ color: ASH, lineHeight: 1.5 }}
        >
          Tell us where you are. We&rsquo;ll tell you which of the four is the
          right place to begin.
        </p>
        <div className="mt-10 flex flex-wrap items-center justify-center gap-5">
          <button
            onClick={onDemoClick}
            className="inline-flex items-center px-8 rounded-full text-base font-medium cursor-pointer transition-all duration-300 hover:-translate-y-0.5 hover:shadow-[0_18px_44px_-16px_rgba(163,197,125,0.45)] active:translate-y-0 active:shadow-none"
            // LEAF-filled, matching StartCapture. The landing had four unrelated
            // button treatments; this collapses them to two — primary filled
            // (leaf) and secondary outlined (the nav's demo pill).
            style={{ backgroundColor: LEAF, color: NOIR, height: 56 }}
          >
            Request a Demo
          </button>
          <a
            href="#index"
            className="inline-flex items-center gap-2 text-base transition-opacity hover:opacity-60"
            style={{ color: BONE }}
          >
            Browse the four
            <span aria-hidden>↑</span>
          </a>
        </div>
      </Reveal>
    </section>
  );
}
