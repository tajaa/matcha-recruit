import { useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";
import { AMBER, ASH, BONE, DISPLAY, LEAF, LINE_D, MATCHA } from "./theme";
import { useReducedMotion } from "./instruments/shared";
import { ProductCarousel } from "./ProductCarousel";
import { StartCapture } from "./StartCapture";

// The headline types itself out like a terminal. Segments keep the per-word
// styling (italic accents) that the old static markup had.
const HEADLINE: { text: string; style?: React.CSSProperties }[] = [
  { text: "We run the whole " },
  { text: "risk", style: { color: AMBER, fontStyle: "italic" } },
  { text: " & " },
  { text: "people", style: { color: MATCHA, fontStyle: "italic" } },
  { text: " function." },
];
const HEADLINE_CHARS = HEADLINE.reduce((n, s) => n + s.text.length, 0);
const TYPE_MS = 38;
const TYPE_DELAY_MS = 620;

// The hero reveals in sequence rather than all at once: masthead, then the
// headline types, then the deck row, then the carousel. Deriving the last two
// from the typing constants keeps the cadence right if the headline changes.
const TYPED_DONE_S = (TYPE_DELAY_MS + HEADLINE_CHARS * TYPE_MS) / 1000;
const MASTHEAD_DELAY_S = 0.15;
const DECK_DELAY_S = TYPED_DONE_S + 0.18;
const CAROUSEL_DELAY_S = DECK_DELAY_S + 0.55;

export function Hero() {
  return (
    <section className="relative w-full min-h-[100svh] flex flex-col">
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

      {/* Masthead row */}
      <div className="max-w-[1600px] mx-auto w-full px-6 sm:px-10 lg:px-16 xl:px-24 pt-[76px] sm:pt-[84px]">
        <div
          className="home-fade"
          style={{ animationDelay: `${MASTHEAD_DELAY_S}s` }}
        >
          <div className="grid grid-cols-2 sm:grid-cols-3 items-center pb-3">
            <span
              className="flex items-center gap-2.5 text-[10.5px] tracking-[0.28em] font-mono uppercase"
              style={{ color: ASH }}
            >
              <span
                className="w-1 h-1 rounded-full shrink-0"
                style={{ backgroundColor: LEAF }}
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
      <div className="relative max-w-[1600px] mx-auto w-full px-6 sm:px-10 lg:px-16 xl:px-24 flex-1 flex flex-col justify-center py-8 sm:py-10">
        <div>
          <div>
            <TypedHeadline />

            {/* Deck row — editorial band under the headline: hairline rule,
                tagline left, work-email capture right. The capture sits above
                the fold on purpose: it's the page's one conversion point. */}
            <div
              className="mt-10 pt-7 border-t flex flex-col lg:flex-row lg:items-end lg:justify-between gap-8 lg:gap-16 home-fade"
              style={{
                borderColor: LINE_D,
                animationDelay: `${DECK_DELAY_S}s`,
              }}
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
              <StartCapture />
            </div>
          </div>

          <div
            className="mt-14 home-fade w-full max-w-[1360px] mx-auto"
            style={{ animationDelay: `${CAROUSEL_DELAY_S}s` }}
          >
            <ProductCarousel startDelayMs={CAROUSEL_DELAY_S * 1000} />
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
    "tracking-[-0.02em] text-[clamp(1.7rem,5.2vw,4.6rem)] xl:text-[clamp(1.9rem,3.4vw,3.4rem)]";
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
            backgroundColor: AMBER,
          }}
        />
      </h1>
    </div>
  );
}
