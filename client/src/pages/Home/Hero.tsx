import { ChevronDown } from "lucide-react";
import { ASH, BONE, DISPLAY, LINE_D, MATCHA } from "./theme";
import { MARQUEE_WORDS } from "./data";
import { ProductCarousel } from "./ProductCarousel";

export function Hero() {
  return (
    <section className="relative w-full min-h-[100svh] flex flex-col">
      {/* Masthead row */}
      <div className="max-w-[1600px] mx-auto w-full px-6 sm:px-10 pt-[76px] sm:pt-[84px]">
        <div className="home-fade" style={{ animationDelay: "0.05s" }}>
          <div className="grid grid-cols-2 sm:grid-cols-3 items-center pb-3">
            <span
              className="flex items-center gap-2.5 text-[10.5px] tracking-[0.28em] font-mono uppercase"
              style={{ color: ASH }}
            >
              <span
                className="w-1 h-1 rounded-full shrink-0"
                style={{ backgroundColor: "#A3C57D" }}
              />
              Managing your risk
            </span>
            <span
              className="hidden sm:block justify-self-center text-[10.5px] tracking-[0.28em] font-mono uppercase"
              style={{ color: ASH }}
            >
              Software · Practitioners
            </span>
            <span
              className="justify-self-end text-[10.5px] tracking-[0.28em] font-mono uppercase tabular-nums"
              style={{ color: ASH }}
            >
              Vol. 01
            </span>
          </div>
          {/* magazine folio — double hairline under the masthead row */}
          <div style={{ height: 1, backgroundColor: LINE_D }} />
          <div
            className="mt-[3px]"
            style={{ height: 1, backgroundColor: LINE_D, opacity: 0.45 }}
          />
        </div>
      </div>

      {/* Ticker — pulled high so it reads immediately, no scroll required */}
      <div>
        <Marquee />
      </div>

      {/* Headline + supporting content, stacked at every breakpoint — the
          carousel sits full-width below the headline/CTAs instead of
          fighting them for space in a side-by-side column. */}
      <div className="relative max-w-[1600px] mx-auto w-full px-6 sm:px-10 flex-1 flex flex-col justify-center py-8 sm:py-10">
        <div>
          <div>
            <h1
              className="home-rise tracking-[-0.02em] text-[clamp(2.2rem,7vw,6.5rem)] xl:text-[clamp(2.4rem,4.7vw,4.7rem)]"
              style={{ fontFamily: DISPLAY, fontWeight: 300, lineHeight: 1.02 }}
            >
              <span style={{ animationDelay: "0.16s" }}>We run the whole</span>{" "}
              <span
                style={{
                  animationDelay: "0.36s",
                  color: "#D97706",
                  fontStyle: "italic",
                }}
              >
                risk
              </span>
              <span style={{ animationDelay: "0.44s" }}>&nbsp;&amp;&nbsp;</span>
              <span
                style={{
                  animationDelay: "0.54s",
                  color: MATCHA,
                  fontStyle: "italic",
                }}
              >
                people
              </span>
              <span style={{ animationDelay: "0.62s" }}>&nbsp;function.</span>
            </h1>

            {/* Deck row — editorial band under the headline: hairline rule,
                tagline left, the starting-line cue right as a circled arrow. */}
            <div
              className="mt-10 pt-7 border-t flex flex-col lg:flex-row lg:items-end lg:justify-between gap-8 home-fade"
              style={{ borderColor: LINE_D, animationDelay: "0.66s" }}
            >
              <p
                className="max-w-3xl text-xl sm:text-2xl"
                style={{ color: BONE, lineHeight: 1.5 }}
              >
                <span style={{ color: "#FFFFFF" }}>
                  Managing your risk before your risk manages you.
                </span>{" "}
                <span style={{ color: ASH }}>
                  Workplace safety, compliance, and risk analysis.
                </span>
              </p>
              <a
                href="#index"
                className="group inline-flex items-center gap-3.5 shrink-0 pb-1"
              >
                <span
                  className="text-[11px] font-mono uppercase tracking-[0.22em] transition-colors duration-200"
                  style={{ color: BONE }}
                >
                  Find your starting line
                </span>
                <span
                  aria-hidden
                  className="flex items-center justify-center w-9 h-9 rounded-full border transition-colors duration-200 group-hover:bg-[#A3C57D] group-hover:border-[#A3C57D] group-hover:text-[#0E0E0C]"
                  style={{ borderColor: LINE_D, color: ASH }}
                >
                  ↓
                </span>
              </a>
            </div>
          </div>

          <div
            className="mt-14 home-fade w-full max-w-[1360px] mx-auto"
            style={{ animationDelay: "0.8s" }}
          >
            <ProductCarousel />
          </div>
        </div>
      </div>

      {/* Scroll cue — blinking chevron so it reads as "there's more below" */}
      <a
        href="#index"
        aria-label="Scroll to products"
        className="home-scroll-cue absolute bottom-5 left-1/2 -translate-x-1/2 z-10 hover:opacity-100"
        style={{ color: ASH }}
      >
        <ChevronDown className="w-6 h-6" strokeWidth={1.5} />
      </a>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Marquee
// ---------------------------------------------------------------------------

export function Marquee() {
  const row = [...MARQUEE_WORDS, ...MARQUEE_WORDS];
  return (
    <div
      className="relative overflow-hidden border-y py-[5px] select-none"
      style={{ borderColor: LINE_D, backgroundColor: MATCHA }}
    >
      <div className="home-marquee-track flex w-max items-center whitespace-nowrap">
        {row.map((w, i) => (
          <span key={i} className="flex items-center">
            <span
              className="px-4 text-[clamp(0.5rem,0.85vw,0.78rem)] tracking-tight"
              style={{ fontFamily: DISPLAY, fontWeight: 400, color: "#5C584E" }}
            >
              {w}
            </span>
            <span className="text-[0.5rem]" style={{ color: "#5C584E" }}>
              ✦
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}
