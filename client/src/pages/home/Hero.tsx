import { ASH } from "./theme";
import { CONTAINER } from "./layout";
import { StartCapture } from "./StartCapture";
import { HeroProof } from "./HeroProof";

/**
 * Entrance choreography, in ms.
 *
 * The headline is absent from this table on purpose: it is STATIC and OPAQUE at
 * first paint. It is the LCP element, and Chrome re-records text LCP as the
 * block grows — the old character-by-character typewriter therefore pushed LCP
 * to ~2.14s before any network cost, against a 2.5s "good" threshold, for a
 * purely decorative reason. Anything that animates opacity from 0 is
 * disqualified from being the LCP candidate, so entrance motion belongs to
 * everything BELOW the headline and nothing else.
 *
 * The other half of the old chain was a conversion bug: every delay was derived
 * from the typing constants, so StartCapture — described in its own file as
 * "the page's one conversion point" — began appearing at 2.32s and was fully
 * opaque at 3.32s. It is now settled at 560ms.
 */
const BEAT = {
  subhead: 60,
  capture: 140,
  proof: 240,
} as const;

export function Hero() {
  return (
    // NO viewport-height floor. 100svh, then 88svh, both forced dead space under
    // the proof strip AND pushed the showcase — the strongest asset on the page,
    // and the thing the hero is asking you to believe — entirely below the fold.
    // The hero is now exactly as tall as its content (~400px at 1440x800), so
    // the showcase's top ~300px lands above the fold on a 13" laptop. That peek
    // is also the scroll affordance, which is why the chevron cue is gone.
    <section className="home-hero relative w-full flex flex-col">
      {/* Atmosphere — two whisper-quiet radial glows (leaf upper-left, amber
          lower-right, echoing the headline accents) lift the canvas off flat
          noir. Kept behind the content by DOM order; blur is baked into the
          gradients (no filter) so it costs nothing to composite. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 overflow-hidden"
      >
        <div
          className="absolute"
          style={{
            left: "-12%",
            top: "-18%",
            width: "62%",
            height: "72%",
            background:
              "radial-gradient(50% 50% at 50% 50%, rgba(163,197,125,0.075) 0%, transparent 70%)",
          }}
        />
        <div
          className="absolute"
          style={{
            right: "-14%",
            bottom: "-22%",
            width: "58%",
            height: "68%",
            background:
              "radial-gradient(50% 50% at 50% 50%, rgba(217,119,6,0.055) 0%, transparent 70%)",
          }}
        />
      </div>

      {/* The masthead row that used to sit here ("Managing your risk" /
          "Volatility · Researchers" / "Vol. 01") is gone. Its left label was
          repeated verbatim in the deck copy 60px below, its centre label meant
          nothing to an HR-compliance buyer, and its double hairline visually
          severed the nav from the headline. It cost ~52px of fold plus 80px of
          top padding — reclaimed here for the headline and the proof strip.
          The magazine folio motif survives where it still earns its place, in
          Manifesto.tsx. */}
      <div
        className={`home-hero-body relative ${CONTAINER} flex-1 flex flex-col justify-center pt-[88px] sm:pt-[96px] pb-7`}
      >
        {/* ONE <h1>, in normal flow, full text, opaque. The old implementation
            rendered two — a hidden full-text copy to reserve height plus a
            visible absolutely-positioned typed one — which duplicated the
            headline for crawlers and made the LCP candidate paint blank.

            Single clamp, no breakpoint: the old pair capped at 4.6rem below xl
            and 3.4rem above it, so dragging the window across 1280px shrank the
            headline by 35% at one pixel of resize. */}
        <h1
          className="tracking-[-0.02em] text-[clamp(2.4rem,5.6vw,5rem)] max-w-[19ch] sm:max-w-none"
          style={{ fontFamily: "var(--font-lite)", fontWeight: 300, lineHeight: 1.02 }}
        >
          The operating system for every <span style={{ fontStyle: "italic" }}>location</span>.
        </h1>

        {/* Deck row — subhead left, conversion right. `md:` is the band the
            homepage skipped entirely: this used to be `flex-col lg:flex-row`,
            so from 768-1023px the capture stacked full-width under a narrow
            paragraph on a viewport with room for both. */}
        <div className="home-hero-deck mt-8 flex flex-col md:flex-row md:items-end md:justify-between gap-8 md:gap-12 lg:gap-16">
          <p
            className="home-fade-fast max-w-2xl text-[1.25rem] sm:text-[1.6rem] tracking-[-0.011em]"
            style={{
              fontFamily: "var(--font-lite)",
              fontWeight: 300,
              lineHeight: 1.42,
              animationDelay: `${BEAT.subhead}ms`,
            }}
          >
            <span style={{ color: "#FFFFFF" }}>
              Keep every location current and every shift on track.
            </span>{" "}
            <span style={{ color: ASH, fontStyle: "italic" }}>
              Location-aware compliance, labor-law and break guidance, inventory and cost analysis, and one place for shift notes and completed work.
            </span>
          </p>

          <div
            className="home-hero-capture home-fade-fast w-full md:w-[360px] lg:w-[420px] shrink-0"
            style={{ animationDelay: `${BEAT.capture}ms` }}
          >
            <StartCapture />
          </div>
        </div>

        <HeroProof
          className="home-hero-proof home-fade-fast mt-9"
          style={{ animationDelay: `${BEAT.proof}ms` }}
        />
      </div>
    </section>
  );
}
