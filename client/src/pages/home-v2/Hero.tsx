import { useEffect, useState } from "react";
import { useReducedMotion } from "../home/instruments/shared";
import { CONTAINER, EYEBROW, EYEBROW_END } from "../home/layout";
import { CREAM, DISPLAY, INK, INK_SOFT, LINE, MATCHA, MATCHA_LT, SANS } from "./theme";
import { HERO_DECK, HERO_DOMAINS, HERO_EYEBROW, HERO_FOLIO, HERO_LINE_1, HERO_LINE_2 } from "./data";

// Entrance stagger, ms. The <h1> itself is never in this table — it's the LCP
// element and must be complete + opaque at t=0 (see the comment on the band
// below). Everything else fades up on this beat.
const BEAT = { deck: 120, cta: 200, furniture: 320 } as const;
const SETTLE_DELAY_MS = 200;

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
  const [settled, setSettled] = useState(reduceMotion);

  useEffect(() => {
    if (reduceMotion) return setSettled(true);
    const t = window.setTimeout(() => setSettled(true), SETTLE_DELAY_MS);
    return () => window.clearTimeout(t);
  }, [reduceMotion]);

  return (
    <section className="relative w-full overflow-x-clip" style={{ backgroundColor: CREAM }}>
      {!reduceMotion && (
        <style>{`
          @keyframes homeV2FadeUp {
            from { opacity: 0; transform: translateY(14px); }
            to { opacity: 1; transform: translateY(0); }
          }
        `}</style>
      )}

      <div className={`relative ${CONTAINER} pt-16 sm:pt-24 pb-16 sm:pb-20`}>
        <div className={EYEBROW} style={{ color: INK_SOFT, marginBottom: "1.25rem" }}>
          {HERO_EYEBROW}
        </div>

        {/*
          Two lines, ONE <h1>, full text, opaque at first paint — the noir
          hero's hard-won LCP rule (pages/home/Hero.tsx:8-35) applies here
          unchanged: anything that animates opacity or geometry on the
          headline disqualifies it as the LCP candidate.

          Line two's field is a full-bleed slab: it starts at the true
          viewport edge and stops just past the text, breaking the container
          margin the same way the sentence breaks who's in control. The TEXT
          stays on the container's grid (padding added back via pl-[...]);
          only the field ignores it. Both lines are painted at full geometry
          and full opacity from frame one — the only motion permitted is a
          colour settle on the field's background-color, same trick the noir
          hero uses on its accent words. Never animate width/opacity/transform
          on this block.
        */}
        <h1
          className="tracking-[-0.025em] text-[clamp(2.6rem,6.2vw,5.75rem)] max-w-[15ch]"
          style={{ fontFamily: DISPLAY, fontWeight: 300, lineHeight: 1.06, color: INK }}
        >
          <span className="block">{HERO_LINE_1}</span>
          <span
            className="block w-fit max-w-[100vw] ml-[calc(50%-50vw)] pl-[calc(50vw-50%+1.5rem)] sm:pl-[calc(50vw-50%+2.5rem)] pr-6 sm:pr-8 py-1"
            style={{
              backgroundColor: settled ? MATCHA : MATCHA_LT,
              backgroundImage:
                "linear-gradient(180deg, rgba(255,255,255,0.07), rgba(0,0,0,0.05))",
              color: CREAM,
              transition: reduceMotion ? undefined : "background-color 600ms cubic-bezier(0.16,1,0.3,1)",
            }}
          >
            {HERO_LINE_2}
          </span>
        </h1>

        <FadeUp delayMs={BEAT.deck} reduceMotion={reduceMotion}>
          <p
            className="mt-8 max-w-[46ch] text-[17px]"
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

        <FadeUp delayMs={BEAT.furniture} reduceMotion={reduceMotion}>
          <div className="mt-14 sm:mt-16 pt-6" style={{ borderTop: `1px solid ${LINE}` }}>
            <div className="flex flex-wrap items-baseline justify-between gap-x-8 gap-y-3">
              <div className="flex flex-wrap items-baseline gap-x-8 gap-y-2">
                {HERO_DOMAINS.map((d) => (
                  <span key={d} className={EYEBROW} style={{ color: INK_SOFT }}>
                    {d}
                  </span>
                ))}
              </div>
              <span className={EYEBROW_END} style={{ color: INK_SOFT }}>
                {HERO_FOLIO}
              </span>
            </div>
          </div>
        </FadeUp>
      </div>
    </section>
  );
}
