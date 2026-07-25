import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { AMBER, ASH, BONE, DISPLAY, LEAF, LINE_D } from "../../home/theme";
import { CONTAINER } from "../../home/layout";
import { PlatformInstrument } from "../../home/instruments/PlatformInstrument";

/**
 * Left-aligned editorial, matching Compliance/Hero.tsx's recipe: same
 * CONTAINER, same top-padding math (ticker is gone from this page, nav is
 * 64px), headline static/opaque at first paint. `PlatformInstrument` — home's
 * noir-native composite-risk-index instrument — is imported statically and
 * anchors the hero instead of the old lazy 600px AgentReasoningAnimation
 * panel, which was an LCP hazard above the fold. The reasoning animation
 * isn't dropped — it moves to pillar 04 ("One Brain"), where a live reasoning
 * trace is actually the point, and stays lazy there since it's below the fold.
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
              "radial-gradient(50% 50% at 50% 50%, rgba(163,197,125,0.065) 0%, transparent 70%)",
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
              "radial-gradient(50% 50% at 50% 50%, rgba(217,119,6,0.05) 0%, transparent 70%)",
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
                The full platform
              </span>
            </div>

            <h1
              className="tracking-[-0.02em] text-[clamp(2.1rem,4.6vw,3.8rem)]"
              style={{ fontFamily: DISPLAY, fontWeight: 300, lineHeight: 1.06, color: BONE }}
            >
              One <span style={{ color: LEAF, fontStyle: "italic" }}>brain</span> for the whole{" "}
              <span style={{ color: AMBER, fontStyle: "italic" }}>risk</span> function.
            </h1>

            <p
              className="home-fade-fast mt-6 max-w-lg text-[1.05rem] sm:text-[1.2rem] tracking-[-0.011em]"
              style={{ fontFamily: DISPLAY, fontWeight: 300, lineHeight: 1.45, color: ASH }}
            >
              Safety, compliance, and employee relations — usually three
              siloed systems. Matcha runs them on one platform where every
              signal talks to the others, so your real risk reads as a single
              live number, not twelve disconnected reports.
            </p>

            <div className="home-fade-fast mt-9 flex flex-wrap items-center gap-3 sm:gap-5" style={{ animationDelay: "80ms" }}>
              <button
                type="button"
                onClick={onContactClick}
                className="inline-flex items-center justify-center gap-2 px-6 h-12 rounded-full text-[15px] font-medium transition-opacity hover:opacity-90 cursor-pointer"
                style={{ backgroundColor: LEAF, color: "#14210B" }}
              >
                Book a consultation
                <ArrowRight className="w-4 h-4" />
              </button>
              <Link
                to="/services"
                className="inline-flex items-center h-12 text-[15px] transition-opacity hover:opacity-60"
                style={{ color: BONE }}
              >
                Explore services →
              </Link>
            </div>
          </div>

          <div className="home-fade-fast" style={{ animationDelay: "160ms" }}>
            <PlatformInstrument />
          </div>
        </div>
      </div>

      <div aria-hidden style={{ height: 1, backgroundColor: LINE_D }} />
    </section>
  );
}
