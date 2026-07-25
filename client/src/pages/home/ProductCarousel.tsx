import { useEffect, useLayoutEffect, useRef, useState } from "react";
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

  // Autoplay starts when the carousel is actually ON SCREEN, not on a fixed
  // timer. It used to take a `startDelayMs` matched to the hero's entrance
  // chain, which fired whether or not anyone had scrolled to it — so the first
  // slide could burn its whole turn unseen.
  //
  // threshold 0.2, not 0.35: the showcase now sits at the fold edge by design
  // (see ShowcaseSection), so on a laptop only the instrument's top third is
  // visible at rest. At 0.35 a visitor looking straight at a live product
  // surface would watch it sit frozen on slide 1 until they scrolled.
  const rootRef = useRef<HTMLDivElement>(null);
  const [started, setStarted] = useState(false);
  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setStarted(true);
          io.disconnect();
        }
      },
      { threshold: 0.2 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  // Respect intent: once the visitor drives the carousel themselves, stop
  // yanking it out from under them. This is the one that actually matters.
  const [manual, setManual] = useState(false);

  // A backgrounded tab kept churning framer-motion slide transitions nobody
  // could see.
  const [hidden, setHidden] = useState(
    typeof document !== "undefined" && document.visibilityState === "hidden",
  );
  useEffect(() => {
    const onVis = () => setHidden(document.visibilityState === "hidden");
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, []);

  const goTo = (next: number, dir: number) => {
    setDirection(dir);
    setIndex(
      ((next % CAROUSEL_PRODUCTS.length) + CAROUSEL_PRODUCTS.length) %
        CAROUSEL_PRODUCTS.length,
    );
  };

  const autoplay = started && !paused && !manual && !hidden && !reduceMotion;

  useEffect(() => {
    if (!autoplay) return;
    const t = window.setInterval(() => goTo(index + 1, 1), SHOWCASE_INTERVAL);
    return () => window.clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoplay, index]);

  const slide = CAROUSEL_PRODUCTS[index];
  const Instrument = INSTRUMENT_COMPONENTS[index];

  // Instruments have different natural heights, so the slot snapped on every
  // slide change. Pin it to the tallest instrument seen so far: it grows a few
  // times during the first cycle, then never moves again. Measuring per-slide
  // instead would pump the slot to 0 in the gap AnimatePresence mode="wait"
  // leaves between exit and enter.
  const slotRef = useRef<HTMLDivElement>(null);
  const [slotHeight, setSlotHeight] = useState(0);
  const widthRef = useRef(0);
  useLayoutEffect(() => {
    const el = slotRef.current;
    if (!el) return;
    const measure = () => {
      const { width, height } = el.getBoundingClientRect();
      if (!height) return;
      // A width change means a new layout — reset the high-water mark so the
      // slot can shrink back down rather than keeping a stale desktop height.
      const reset = width !== widthRef.current;
      widthRef.current = width;
      setSlotHeight((prev) => (reset ? height : Math.max(prev, height)));
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const variants = {
    enter: (dir: number) => ({ x: dir > 0 ? 32 : -32, opacity: 0 }),
    center: { x: 0, opacity: 1 },
    exit: (dir: number) => ({ x: dir > 0 ? -32 : 32, opacity: 0 }),
  };

  return (
    <div
      ref={rootRef}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      <div className="flex flex-col lg:flex-row lg:items-center gap-8 lg:gap-12">
        {/* Copy column, LEFT. min-h on the heading slot keeps the View link
            still across 1- vs 2-line names and optional subheaders. */}
        <div className="lg:w-[320px] lg:shrink-0 flex flex-col">
          <div className="min-h-[92px]">
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
                  className="font-mk-mono text-sm shrink-0 pt-1"
                  style={{ color: slide.accent }}
                >
                  {slide.n}
                </span>
                <div className="min-w-0">
                  <h3
                    className="tracking-[-0.02em]"
                    style={{
                      fontFamily: DISPLAY,
                      fontWeight: 400,
                      fontSize:
                        slide.nameSize ?? "clamp(1.75rem, 2.4vw, 2.75rem)",
                      color: BONE,
                    }}
                  >
                    {slide.name}
                  </h3>
                  {slide.subheader && (
                    <p
                      className="text-[11px] sm:text-[12px] font-mk-mono uppercase tracking-[0.14em] mt-1"
                      style={{ color: ASH }}
                    >
                      {slide.subheader}
                    </p>
                  )}
                </div>
              </motion.div>
            </AnimatePresence>
          </div>
          <Link
            to={slide.to}
            className="text-[13px] font-mk-mono uppercase tracking-[0.18em] shrink-0 transition-opacity hover:opacity-60 mt-4 self-start"
            style={{ color: ASH }}
          >
            View →
          </Link>
        </div>

        <MotionConfig reducedMotion="user">
          <Link to={slide.to} className="group block flex-1 min-w-0">
            <motion.div
              initial={false}
              animate={{ height: slotHeight || "auto" }}
              transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
              style={{ overflow: "hidden" }}
            >
              <div ref={slotRef}>
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
              </div>
            </motion.div>
          </Link>
        </MotionConfig>
      </div>

      <div className="mt-4 flex items-center gap-2">
        {CAROUSEL_PRODUCTS.map((s, i) => (
          <button
            key={i}
            type="button"
            aria-label={`Go to ${s.name}`}
            onClick={() => {
              setManual(true);
              goTo(i, i > index ? 1 : -1);
            }}
            // The visible bar is 6px tall — far under Apple's 44pt minimum, and
            // these are the carousel's only touch control. The ::after pseudo
            // element expands the hit area to ~46px tall and out to the gap on
            // each side, so the whole dot row is one contiguous tappable strip
            // with no dead zones, WITHOUT changing the layout the bars sit in.
            // `overflow-hidden` moved to the inner span: on the button it would
            // clip the pseudo element and undo the whole thing.
            className="relative h-1.5 rounded-full transition-all duration-300 cursor-pointer after:absolute after:content-[''] after:-inset-x-1 after:-inset-y-5"
            style={{
              width: i === index ? 28 : 8,
              backgroundColor: i === index ? "rgba(245,242,237,0.18)" : LINE_D,
            }}
          >
            <span className="absolute inset-0 rounded-full overflow-hidden">
              {i === index && autoplay && (
                <span
                  key={index}
                  className="absolute inset-0 origin-left"
                  style={{
                    backgroundColor: s.accent,
                    animation: `showcaseProgress ${SHOWCASE_INTERVAL}ms linear`,
                  }}
                />
              )}
              {i === index && !autoplay && (
                <span
                  className="absolute inset-0"
                  style={{ backgroundColor: s.accent }}
                />
              )}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
