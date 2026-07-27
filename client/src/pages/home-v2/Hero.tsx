import { useEffect, useState } from "react";
import { useReducedMotion } from "../home/instruments/shared";
import { CONTAINER } from "../home/layout";
import { CREAM, DISPLAY, INK, INK_SOFT, MATCHA, MATCHA_LT } from "./theme";
import { HERO_DECK, HERO_LINE_1, HERO_LINE_2 } from "./data";

// Settle timing for the one permitted flourish — see the note below. Mirrors
// pages/home/Hero.tsx's ACCENT_SETTLE_MS pattern for the same reason: the
// headline is the LCP element and must be complete + opaque at t=0.
const SETTLE_DELAY_MS = 200;

export function Hero({ onDemoClick }: { onDemoClick?: () => void }) {
  const reduceMotion = useReducedMotion();
  const [settled, setSettled] = useState(reduceMotion);

  useEffect(() => {
    if (reduceMotion) return setSettled(true);
    const t = window.setTimeout(() => setSettled(true), SETTLE_DELAY_MS);
    return () => window.clearTimeout(t);
  }, [reduceMotion]);

  return (
    <section className="relative w-full" style={{ backgroundColor: CREAM }}>
      <div className={`relative ${CONTAINER} pt-16 sm:pt-24 pb-16 sm:pb-20`}>
        {/*
          Two lines, ONE <h1>, full text, opaque at first paint — the noir
          hero's hard-won LCP rule (pages/home/Hero.tsx:8-35) applies here
          unchanged: anything that animates opacity or geometry on the
          headline disqualifies it as the LCP candidate. Line two's block is
          painted at full size and full opacity from frame one; the only
          motion permitted is a colour settle on its background, the same
          trick the noir hero uses on its accent words.
        */}
        <h1
          className="tracking-[-0.02em] text-[clamp(2.3rem,5.4vw,4.5rem)] max-w-[16ch]"
          style={{ fontFamily: DISPLAY, fontWeight: 300, lineHeight: 1.12, color: INK }}
        >
          {HERO_LINE_1}
          <br />
          <span
            className="inline-block px-3 py-0.5 -ml-1"
            style={{
              backgroundColor: settled ? MATCHA : MATCHA_LT,
              color: CREAM,
              borderRadius: "4px 22px 4px 4px",
              transition: reduceMotion ? undefined : "background-color 600ms cubic-bezier(0.16,1,0.3,1)",
            }}
          >
            {HERO_LINE_2}
          </span>
        </h1>

        <div className="mt-8 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-8">
          <p
            className="max-w-lg text-[1.1rem] sm:text-[1.3rem] tracking-[-0.011em]"
            style={{ fontFamily: DISPLAY, fontWeight: 300, lineHeight: 1.45, color: INK_SOFT }}
          >
            {HERO_DECK}
          </p>

          <div className="flex items-center gap-6 shrink-0">
            <button
              type="button"
              onClick={onDemoClick}
              className="inline-flex items-center justify-center h-12 px-7 text-[15px] font-medium cursor-pointer transition-opacity hover:opacity-90"
              style={{ backgroundColor: MATCHA, color: CREAM, borderRadius: "999px 6px 999px 999px" }}
            >
              Get a demo
            </button>
            <a
              href="#"
              className="text-[15px] transition-opacity hover:opacity-60"
              style={{ color: INK }}
            >
              See how it works →
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}
