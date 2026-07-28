import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { ASH, BONE, LEAF, LINE_D } from "../../home/theme";
import { CONTAINER } from "../../home/layout";
import { DailyInstrument } from "../../home/instruments/DailyInstrument";

/**
 * Left-aligned editorial, matching Compliance/Hero.tsx and Platform/Hero.tsx's
 * recipe. Headline makes a claim instead of naming the product — "Matcha
 * Lite." told a visitor nothing they didn't already know from the nav link
 * they clicked. `DailyInstrument` — home's noir-native magic-link intake
 * instrument — is imported statically and anchors the hero instead of the old
 * lazy RiskInsightsHero (recharts + d3, ~100-150 KB gz, an LCP hazard above
 * the fold with no other importers on the site).
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
                Built for daily use, not a once-a-year binder
              </span>
            </div>

            <h1
              className="tracking-[-0.02em] text-[clamp(2.1rem,4.4vw,3.6rem)]"
              style={{ fontFamily: "var(--font-lite)", fontWeight: 300, lineHeight: 1.08, color: BONE }}
            >
              The everyday{" "}
              <span style={{ fontStyle: "italic" }}>intake layer</span>{" "}
              for a team with{" "}
              <span style={{ fontStyle: "italic" }}>no time</span> for
              one.
            </h1>

            <p
              className="home-fade-fast mt-6 max-w-lg text-[1.05rem] sm:text-[1.2rem] tracking-[-0.011em]"
              style={{ fontFamily: "var(--font-lite)", fontWeight: 300, lineHeight: 1.45, color: ASH }}
            >
              A magic link anyone can text, type into, or talk into. OSHA logs
              that fill themselves, risk insights from your own data, and a
              full HR library underneath.
            </p>

            <div className="home-fade-fast mt-9 flex flex-wrap items-center gap-3 sm:gap-5" style={{ animationDelay: "80ms" }}>
              <Link
                to="/lite/signup"
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
            <DailyInstrument numberFont="var(--font-lite)" />
          </div>
        </div>
      </div>
    </section>
  );
}
