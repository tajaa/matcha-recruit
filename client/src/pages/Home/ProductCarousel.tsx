import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AnimatePresence, motion, MotionConfig } from "framer-motion";
import { CAROUSEL_PRODUCTS } from "./data";
import { ASH, BONE, DISPLAY, LINE_D } from "./theme";
import { useReducedMotion } from "./instruments/shared";
import { ComplianceInstrument } from "./instruments/ComplianceInstrument";
import { DailyInstrument } from "./instruments/DailyInstrument";
import { OshaLogInstrument } from "./instruments/OshaLogInstrument";
import { PlatformInstrument } from "./instruments/PlatformInstrument";

export const INSTRUMENT_COMPONENTS = [
  DailyInstrument,
  OshaLogInstrument,
  ComplianceInstrument,
  PlatformInstrument,
];
export const SHOWCASE_INTERVAL = 6000;

export function ProductCarousel() {
  const [index, setIndex] = useState(0);
  const [direction, setDirection] = useState(1);
  const [paused, setPaused] = useState(false);
  const reduceMotion = useReducedMotion();

  const goTo = (next: number, dir: number) => {
    setDirection(dir);
    setIndex(
      ((next % CAROUSEL_PRODUCTS.length) + CAROUSEL_PRODUCTS.length) %
        CAROUSEL_PRODUCTS.length,
    );
  };

  useEffect(() => {
    if (paused || reduceMotion) return;
    const t = window.setInterval(() => goTo(index + 1, 1), SHOWCASE_INTERVAL);
    return () => window.clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paused, index, reduceMotion]);

  const slide = CAROUSEL_PRODUCTS[index];
  const Instrument = INSTRUMENT_COMPONENTS[index];

  const variants = {
    enter: (dir: number) => ({ x: dir > 0 ? 32 : -32, opacity: 0 }),
    center: { x: 0, opacity: 1 },
    exit: (dir: number) => ({ x: dir > 0 ? -32 : 32, opacity: 0 }),
  };

  return (
    <div
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      {/* What you're about to see, ABOVE the card. Fixed-height slot so the
          heading (1- vs 2-line names + optional subheader) never reflows the
          card below it as slides change. */}
      <div className="flex items-start justify-between gap-4 mb-5 h-[72px]">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={index}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.3 }}
            className="flex items-start gap-3 min-w-0"
          >
            <span
              className="font-mono text-sm shrink-0 pt-1"
              style={{ color: slide.accent }}
            >
              {slide.n}
            </span>
            <div className="min-w-0">
              <h3
                className="tracking-[-0.02em] truncate"
                style={{
                  fontFamily: DISPLAY,
                  fontWeight: 400,
                  fontSize: slide.nameSize ?? "clamp(1.75rem, 2.4vw, 2.75rem)",
                  color: BONE,
                }}
              >
                {slide.name}
              </h3>
              {slide.subheader && (
                <p
                  className="text-[11px] sm:text-[12px] font-mono uppercase tracking-[0.14em] mt-1 truncate"
                  style={{ color: ASH }}
                >
                  {slide.subheader}
                </p>
              )}
            </div>
          </motion.div>
        </AnimatePresence>
        <Link
          to={slide.to}
          className="text-[13px] font-mono uppercase tracking-[0.18em] shrink-0 transition-opacity hover:opacity-60"
          style={{ color: ASH }}
        >
          View →
        </Link>
      </div>

      <MotionConfig reducedMotion="user">
        <Link to={slide.to} className="group block">
          <AnimatePresence mode="wait" custom={direction} initial={false}>
            <motion.div
              key={index}
              custom={direction}
              variants={variants}
              initial="enter"
              animate="center"
              exit="exit"
              transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
            >
              <Instrument />
            </motion.div>
          </AnimatePresence>
        </Link>
      </MotionConfig>

      <div className="mt-4 flex items-center gap-2">
        {CAROUSEL_PRODUCTS.map((s, i) => (
          <button
            key={i}
            type="button"
            aria-label={`Go to ${s.name}`}
            onClick={() => goTo(i, i > index ? 1 : -1)}
            className="relative h-1.5 rounded-full overflow-hidden transition-all duration-300"
            style={{
              width: i === index ? 28 : 8,
              backgroundColor: i === index ? "rgba(245,242,237,0.18)" : LINE_D,
            }}
          >
            {i === index && !paused && !reduceMotion && (
              <span
                key={index}
                className="absolute inset-0 origin-left"
                style={{
                  backgroundColor: s.accent,
                  animation: `showcaseProgress ${SHOWCASE_INTERVAL}ms linear`,
                }}
              />
            )}
            {i === index && (paused || reduceMotion) && (
              <span
                className="absolute inset-0"
                style={{ backgroundColor: s.accent }}
              />
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
