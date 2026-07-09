import { useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";
import { ASH, BONE, DISPLAY, LINE_D, MATCHA } from "./theme";
import { useReducedMotion } from "./instruments/shared";
import { ProductCarousel } from "./ProductCarousel";

// The headline types itself out like a terminal. Segments keep the per-word
// styling (italic accents) that the old static markup had.
const HEADLINE: { text: string; style?: React.CSSProperties }[] = [
  { text: "We run the whole " },
  { text: "risk", style: { color: "#D97706", fontStyle: "italic" } },
  { text: " & " },
  { text: "people", style: { color: MATCHA, fontStyle: "italic" } },
  { text: " function." },
];
const HEADLINE_CHARS = HEADLINE.reduce((n, s) => n + s.text.length, 0);
const TYPE_MS = 42;
const TYPE_DELAY_MS = 400;

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
              Volatility · Researchers
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

      {/* Headline + supporting content, stacked at every breakpoint — the
          carousel sits full-width below the headline/CTAs instead of
          fighting them for space in a side-by-side column. */}
      <div className="relative max-w-[1600px] mx-auto w-full px-6 sm:px-10 flex-1 flex flex-col justify-center py-8 sm:py-10">
        <div>
          <div>
            <TypedHeadline />

            {/* Deck row — editorial band under the headline: hairline rule,
                tagline left, the starting-line cue right as a circled arrow. */}
            <div
              className="mt-10 pt-7 border-t flex flex-col lg:flex-row lg:items-end lg:justify-between gap-8 home-fade"
              style={{ borderColor: LINE_D, animationDelay: "0.66s" }}
            >
              <p
                className="max-w-3xl text-[1.35rem] sm:text-[1.75rem] tracking-[-0.011em]"
                style={{
                  fontFamily: DISPLAY,
                  fontWeight: 300,
                  color: BONE,
                  lineHeight: 1.42,
                }}
              >
                <span style={{ color: "#FFFFFF" }}>
                  Managing your risk before your risk manages you.
                </span>{" "}
                <span style={{ color: ASH, fontStyle: "italic" }}>
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
        className="home-scroll-cue absolute bottom-14 left-1/2 -translate-x-1/2 z-10 hover:opacity-100"
        style={{ color: ASH }}
      >
        <ChevronDown className="w-8 h-8" strokeWidth={1.5} />
      </a>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Typed headline
// ---------------------------------------------------------------------------

function TypedHeadline() {
  const reduceMotion = useReducedMotion();
  const [typed, setTyped] = useState(0);

  useEffect(() => {
    if (reduceMotion) {
      setTyped(HEADLINE_CHARS);
      return;
    }
    let timer = 0;
    const start = window.setTimeout(() => {
      timer = window.setInterval(() => {
        setTyped((n) => {
          if (n >= HEADLINE_CHARS) {
            window.clearInterval(timer);
            return n;
          }
          return n + 1;
        });
      }, TYPE_MS);
    }, TYPE_DELAY_MS);
    return () => {
      window.clearTimeout(start);
      window.clearInterval(timer);
    };
  }, [reduceMotion]);

  const cls =
    "tracking-[-0.02em] text-[clamp(1.9rem,6vw,5.4rem)] xl:text-[clamp(2.1rem,4vw,4rem)]";
  const font: React.CSSProperties = {
    fontFamily: DISPLAY,
    fontWeight: 300,
    lineHeight: 1.02,
    whiteSpace: "pre-wrap",
  };

  // Reveal by slicing each segment against a running character cursor.
  let cursor = 0;

  return (
    // A hidden full-text copy holds the final height so the deck row and
    // carousel below don't reflow line-by-line as the headline types.
    <div className="relative">
      <h1 aria-hidden className={cls} style={{ ...font, visibility: "hidden" }}>
        {HEADLINE.map((s, i) => (
          <span key={i} style={s.style}>
            {s.text}
          </span>
        ))}
      </h1>
      <h1
        className={`${cls} absolute inset-0`}
        style={font}
        aria-label={HEADLINE.map((s) => s.text).join("")}
      >
        {HEADLINE.map((s, i) => {
          const shown = s.text.slice(0, Math.max(0, typed - cursor));
          cursor += s.text.length;
          return (
            <span key={i} style={s.style}>
              {shown}
            </span>
          );
        })}
        <span
          aria-hidden
          className="home-caret inline-block align-baseline"
          style={{
            width: "0.055em",
            height: "0.78em",
            marginLeft: "0.05em",
            backgroundColor: "#D97706",
          }}
        />
      </h1>
    </div>
  );
}
