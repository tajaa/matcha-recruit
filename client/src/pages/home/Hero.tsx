import { useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";
import { AMBER, ASH, BONE, DISPLAY, LEAF, LINE_D } from "./theme";
import { CONTAINER } from "./layout";
import { useReducedMotion } from "./instruments/shared";
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

/**
 * The one editorial flourish that survives, because it is LCP-safe: the two
 * accent words paint in bone with the rest of the headline (so the LCP text is
 * complete at t=0) and only their HUE moves afterwards. No layout, no opacity.
 */
const ACCENT_SETTLE_MS = 200;

export function Hero() {
  const reduceMotion = useReducedMotion();
  const [accented, setAccented] = useState(reduceMotion);

  useEffect(() => {
    if (reduceMotion) return setAccented(true);
    const t = window.setTimeout(() => setAccented(true), ACCENT_SETTLE_MS);
    return () => window.clearTimeout(t);
  }, [reduceMotion]);

  const accent = (color: string): React.CSSProperties => ({
    color: accented ? color : BONE,
    fontStyle: "italic",
    transition: reduceMotion ? undefined : "color 600ms cubic-bezier(0.16,1,0.3,1)",
  });

  return (
    // 88svh, not 100: with the masthead and the carousel both gone the hero's
    // content no longer fills a full viewport, and a rigid 100svh left ~230px
    // of dead space under the proof strip that read as unfinished rather than
    // airy. Letting the showcase peek above the fold also signals scrollability
    // better than the chevron does.
    <section className="home-hero relative w-full min-h-[88svh] flex flex-col">
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
        className={`home-hero-body relative ${CONTAINER} flex-1 flex flex-col justify-center pt-[104px] sm:pt-[112px] pb-10`}
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
          style={{ fontFamily: DISPLAY, fontWeight: 300, lineHeight: 1.02 }}
        >
          We run the whole <span style={accent(AMBER)}>risk</span> &amp;{" "}
          <span style={accent(LEAF)}>people</span> function.
        </h1>

        {/* Deck row — subhead left, conversion right. `md:` is the band the
            homepage skipped entirely: this used to be `flex-col lg:flex-row`,
            so from 768-1023px the capture stacked full-width under a narrow
            paragraph on a viewport with room for both. */}
        <div className="home-hero-deck mt-9 flex flex-col md:flex-row md:items-end md:justify-between gap-8 md:gap-12 lg:gap-16">
          <p
            className="home-fade-fast max-w-2xl text-[1.25rem] sm:text-[1.6rem] tracking-[-0.011em]"
            style={{
              fontFamily: DISPLAY,
              fontWeight: 300,
              lineHeight: 1.42,
              animationDelay: `${BEAT.subhead}ms`,
            }}
          >
            <span style={{ color: "#FFFFFF" }}>
              Managing your risk before your risk manages you.
            </span>{" "}
            <span style={{ color: ASH, fontStyle: "italic" }}>
              Workplace safety, compliance, and risk analysis.
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
          className="home-hero-proof home-fade-fast mt-12"
          style={{ animationDelay: `${BEAT.proof}ms` }}
        />
      </div>

      {/* Scroll cue — in normal flow as the section's last flex child, not
          `absolute bottom-14`. The content block above is `flex-1`, so the cue
          is pushed to the bottom of the 100svh section and cannot land on top
          of content at any viewport height. The absolute version overlapped the
          carousel on laptop-height screens. */}
      <a
        href="#showcase"
        aria-label="Scroll to product showcase"
        // px-4 widens the hit area to 64px; the icon alone was 32px wide.
        className="home-scroll-cue mx-auto shrink-0 px-4 pb-10 hover:opacity-100"
        style={{ color: ASH }}
      >
        <ChevronDown className="w-8 h-8" strokeWidth={1.5} />
      </a>

      <div aria-hidden style={{ height: 1, backgroundColor: LINE_D }} />
    </section>
  );
}
