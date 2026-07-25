import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { AMBER, ASH, BONE, DISPLAY, LEAF, LINE_D } from "../../home/theme";
import { CONTAINER } from "../../home/layout";
import { ComplianceInstrument } from "../../home/instruments/ComplianceInstrument";
import { HERO_DECK, HERO_EYEBROW, HERO_HEADLINE_PARTS } from "./data";

/**
 * Hero — left-aligned editorial, matching `pages/home/Hero.tsx`'s recipe
 * exactly (same CONTAINER, same top padding math, same fade beats), with the
 * live compliance instrument standing in for StartCapture as the right-hand
 * anchor. Unlike home, this hero's headline makes a coverage claim rather than
 * naming the company — "Matcha Compliance." told a visitor nothing they didn't
 * already know from the nav link they just clicked.
 *
 * No LCP-typing risk here either: headline is static/opaque at first paint,
 * same as home's.
 */
export function Hero({ onContactClick }: { onContactClick: () => void }) {
  return (
    <section className="home-hero relative w-full flex flex-col">
      <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
        <div
          className="absolute"
          style={{
            left: "-12%",
            top: "-18%",
            width: "62%",
            height: "72%",
            background:
              "radial-gradient(50% 50% at 50% 50%, rgba(226,114,91,0.06) 0%, transparent 70%)",
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
              "radial-gradient(50% 50% at 50% 50%, rgba(163,197,125,0.055) 0%, transparent 70%)",
          }}
        />
      </div>

      <div
        className={`home-hero-body relative ${CONTAINER} flex-1 flex flex-col justify-center pt-[88px] sm:pt-[96px] pb-10`}
      >
        <div className="grid grid-cols-1 lg:grid-cols-[1.1fr_1fr] gap-10 lg:gap-14 items-center">
          <div>
            <div
              className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full mb-6"
              style={{ border: `1px solid ${LINE_D}`, color: ASH }}
            >
              <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: LEAF }} />
              <span className="text-[10px] sm:text-[11px] font-mk-mono uppercase tracking-[0.18em]">
                {HERO_EYEBROW}
              </span>
            </div>

            <h1
              className="tracking-[-0.02em] text-[clamp(2.1rem,4.4vw,3.6rem)]"
              style={{ fontFamily: DISPLAY, fontWeight: 300, lineHeight: 1.08, color: BONE }}
            >
              {HERO_HEADLINE_PARTS.lead}
              <span style={{ color: LEAF, fontStyle: "italic" }}>
                {HERO_HEADLINE_PARTS.accent1}
              </span>
              {HERO_HEADLINE_PARTS.mid}
              <span style={{ color: AMBER, fontStyle: "italic" }}>
                {HERO_HEADLINE_PARTS.accent2}
              </span>
              {HERO_HEADLINE_PARTS.tail}
            </h1>

            <p
              className="home-fade-fast mt-6 max-w-lg text-[1.05rem] sm:text-[1.2rem] tracking-[-0.011em]"
              style={{ fontFamily: DISPLAY, fontWeight: 300, lineHeight: 1.45, color: ASH }}
            >
              {HERO_DECK}
            </p>

            <div className="home-fade-fast mt-9 flex flex-wrap items-center gap-3 sm:gap-5" style={{ animationDelay: "80ms" }}>
              <Link
                to="/compliance/signup"
                className="inline-flex items-center justify-center gap-2 px-6 h-12 rounded-full text-[15px] font-medium transition-opacity hover:opacity-90"
                style={{ backgroundColor: LEAF, color: "#14210B" }}
              >
                Start now
                <ArrowRight className="w-4 h-4" />
              </Link>
              <button
                type="button"
                onClick={onContactClick}
                className="inline-flex items-center h-12 text-[15px] transition-opacity hover:opacity-60 cursor-pointer"
                style={{ color: BONE }}
              >
                Talk to sales
              </button>
            </div>
          </div>

          <div className="home-fade-fast" style={{ animationDelay: "160ms" }}>
            <ComplianceInstrument />
          </div>
        </div>
      </div>

      <div aria-hidden style={{ height: 1, backgroundColor: LINE_D }} />
    </section>
  );
}
