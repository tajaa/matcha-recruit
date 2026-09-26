import { Accent } from "../../components/marketing/kit/Chrome";
import { display } from "../../components/marketing/kit/styles";
import { BOARD, PAPER, hexA } from "../../components/marketing/kit/theme";
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
    <section className="home-hero sched-dark relative w-full flex flex-col" style={{ backgroundColor: BOARD.PAPER, color: PAPER }}>
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
          className="max-w-[19ch] sm:max-w-none"
          style={{ ...display, fontSize: "clamp(2.75rem, 6vw, 5.75rem)", lineHeight: 0.98 }}
        >
          We run the whole risk &amp; <Accent dark>people</Accent> function.
        </h1>

        {/* Deck row — subhead left, conversion right. `md:` is the band the
            homepage skipped entirely: this used to be `flex-col lg:flex-row`,
            so from 768-1023px the capture stacked full-width under a narrow
            paragraph on a viewport with room for both. */}
        <div className="home-hero-deck mt-8 flex flex-col md:flex-row md:items-end md:justify-between gap-8 md:gap-12 lg:gap-16">
          <p
            className="cut-fade cut-fade-fast max-w-2xl text-[1.2rem] sm:text-[1.45rem] tracking-[-0.011em]"
            style={{ lineHeight: 1.45, ["--d" as string]: `${BEAT.subhead}ms` }}
          >
            <span style={{ color: PAPER }}>
              Managing your risk before your risk manages you.
            </span>{" "}
            <span style={{ color: hexA(PAPER, 0.58) }}>
              Workplace safety, compliance, and risk analysis.
            </span>
          </p>

          <div
            className="home-hero-capture cut-fade cut-fade-fast w-full md:w-[360px] lg:w-[420px] shrink-0"
            style={{ ["--d" as string]: `${BEAT.capture}ms` }}
          >
            <StartCapture />
          </div>
        </div>

        <HeroProof
          className="home-hero-proof cut-fade cut-fade-fast mt-9"
          style={{ ["--d" as string]: `${BEAT.proof}ms` }}
        />
      </div>
    </section>
  );
}
