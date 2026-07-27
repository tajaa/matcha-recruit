import { useEffect, useState } from "react";
import { useReducedMotion } from "../home/instruments/shared";
import { CONTAINER, EYEBROW } from "../home/layout";
import { CREAM, DISPLAY, INK, INK_SOFT, LINE, MATCHA, SANS } from "./theme";
import { paperLayers, paperSurface } from "./PaperGrain";
import { HERO_DECK, HERO_DOMAINS, HERO_EYEBROW, HERO_LINE_1, HERO_LINE_2 } from "./data";

// Entrance stagger, ms. The <h1> itself is never in this table — it's the LCP
// element and must be complete + opaque at t=0 (see the comment on the band
// below). Everything else fades up on this beat.
const BEAT = { deck: 120, cta: 200, domains: 280 } as const;
const WIPE_DELAY_MS = 250;

// Shared box for both the base line-2 text and its inverted overlay — MUST
// stay identical between the two or the overlay re-wraps differently than
// the base and the clip-path reveal tears.
const BAND_BOX =
  "block w-fit max-w-[100vw] ml-[calc(50%-50vw)] pl-[calc(50vw-50%+1.5rem)] sm:pl-[calc(50vw-50%+2.5rem)] pr-6 sm:pr-8 py-2";

function FadeUp({
  children,
  delayMs,
  reduceMotion,
}: {
  children: React.ReactNode;
  delayMs: number;
  reduceMotion: boolean;
}) {
  return (
    <div
      style={
        reduceMotion
          ? undefined
          : {
              opacity: 0,
              animation: "homeV2FadeUp 0.5s cubic-bezier(0.16,1,0.3,1) forwards",
              animationDelay: `${delayMs}ms`,
            }
      }
    >
      {children}
    </div>
  );
}

export function Hero({ onDemoClick }: { onDemoClick?: () => void }) {
  const reduceMotion = useReducedMotion();
  const [revealed, setRevealed] = useState(reduceMotion);

  useEffect(() => {
    if (reduceMotion) return setRevealed(true);
    const t = window.setTimeout(() => setRevealed(true), WIPE_DELAY_MS);
    return () => window.clearTimeout(t);
  }, [reduceMotion]);

  return (
    <section
      className="relative w-full overflow-x-clip"
      style={{ ...paperSurface(CREAM), borderBottom: `1px solid ${LINE}` }}
    >
      {!reduceMotion && (
        <style>{`
          @keyframes homeV2FadeUp {
            from { opacity: 0; transform: translateY(14px); }
            to { opacity: 1; transform: translateY(0); }
          }
        `}</style>
      )}

      <div className={`relative ${CONTAINER} pt-16 sm:pt-24 pb-20 sm:pb-24`}>
        <div className={EYEBROW} style={{ color: INK_SOFT, marginBottom: "1.25rem" }}>
          {HERO_EYEBROW}
        </div>

        {/*
          Two lines, ONE <h1>, full text, opaque at first paint — the noir
          hero's hard-won LCP rule (pages/home/Hero.tsx:8-35) applies here
          unchanged: anything that animates opacity or geometry on the
          headline disqualifies it as the LCP candidate. No max-width on the
          h1: each half is its own block span, so the two-part break is
          structural, not a wrap artifact — a wrap width here would let a
          narrower viewport fold the chiasmus into three lines and destroy
          the exact structure the treatment exists to show.

          Line two is TWO stacked copies of the same text in the same box
          (BAND_BOX, applied identically to both so neither can wrap
          differently than the other): a real ink-on-cream base underneath,
          and an absolutely-positioned cream-on-green overlay whose
          `clip-path` wipes in from the left. The overlay is `aria-hidden`
          decoration — the base is what a screen reader and the LCP recorder
          see, painted at full opacity and final position from frame one.
          Nothing about the headline's own geometry ever animates; only the
          overlay's clip-path moves, on the compositor.
        */}
        <h1
          className="tracking-[-0.025em] text-[clamp(1.9rem,5.2vw,5rem)]"
          style={{ fontFamily: DISPLAY, fontWeight: 300, lineHeight: 1.2, color: INK }}
        >
          <span className="block">{HERO_LINE_1}</span>
          <span className={`relative ${BAND_BOX}`}>
            {HERO_LINE_2}
            <span
              aria-hidden
              className={`absolute inset-0 ${BAND_BOX}`}
              style={{
                backgroundColor: MATCHA,
                backgroundImage: `${paperLayers().backgroundImage}, linear-gradient(180deg, rgba(255,255,255,0.07), rgba(0,0,0,0.05))`,
                backgroundSize: `${paperLayers().backgroundSize}, 100% 100%`,
                backgroundBlendMode: "overlay, overlay, normal",
                color: CREAM,
                clipPath: revealed ? "inset(0 0 0 0)" : "inset(0 100% 0 0)",
                transition: reduceMotion ? undefined : "clip-path 900ms cubic-bezier(0.65,0,0.2,1)",
              }}
            >
              {HERO_LINE_2}
            </span>
          </span>
        </h1>

        <div className="mt-10 grid grid-cols-1 lg:grid-cols-[1.15fr_auto] gap-12 lg:gap-20">
          <div>
            <FadeUp delayMs={BEAT.deck} reduceMotion={reduceMotion}>
              <p
                className="max-w-[38ch] text-[17px]"
                style={{ fontFamily: SANS, fontWeight: 350, lineHeight: 1.65, color: INK_SOFT }}
              >
                {HERO_DECK}
              </p>
            </FadeUp>

            <FadeUp delayMs={BEAT.cta} reduceMotion={reduceMotion}>
              <div className="mt-8 flex items-center gap-6">
                <button
                  type="button"
                  onClick={onDemoClick}
                  className="inline-flex items-center justify-center h-12 px-7 rounded-[6px] text-[15px] font-medium cursor-pointer transition-opacity hover:opacity-90"
                  style={{
                    backgroundColor: MATCHA,
                    color: CREAM,
                    boxShadow: "0 1px 2px rgba(20,21,15,0.16)",
                  }}
                >
                  Get a demo
                </button>
                <a
                  href="#"
                  className="inline-block text-[15px] pb-0.5 transition-opacity hover:opacity-60"
                  style={{ color: INK, borderBottom: `1px solid ${LINE}` }}
                >
                  See how it works →
                </a>
              </div>
            </FadeUp>
          </div>

          <FadeUp delayMs={BEAT.domains} reduceMotion={reduceMotion}>
            <div className="lg:w-[280px] flex flex-col">
              {HERO_DOMAINS.map((d, i) => (
                <div
                  key={d.label}
                  className="py-4"
                  style={i > 0 ? { borderTop: `1px solid ${LINE}` } : undefined}
                >
                  <div className={EYEBROW} style={{ color: INK }}>
                    {d.label}
                  </div>
                  <div
                    className="mt-1.5 text-[13.5px] leading-snug"
                    style={{ fontFamily: SANS, color: INK_SOFT }}
                  >
                    {d.caption}
                  </div>
                </div>
              ))}
            </div>
          </FadeUp>
        </div>
      </div>
    </section>
  );
}
