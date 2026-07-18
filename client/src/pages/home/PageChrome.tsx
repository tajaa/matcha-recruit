import { useEffect, useRef, useState } from "react";
import { LEAF } from "./theme";
import { useReducedMotion } from "./instruments/shared";

export function GrainOverlay() {
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-0 z-[60]"
      style={{
        backgroundImage: "url('/textures/asfalt-light.png')",
        backgroundRepeat: "repeat",
        opacity: 0.05,
        mixBlendMode: "soft-light",
      }}
    />
  );
}

/**
 * Scroll-reveal wrapper — fades + rises a section's content in the first time
 * it enters the viewport, so the page below the fold feels as authored as the
 * hero's sequenced entrance. Respects prefers-reduced-motion (renders shown).
 */
export function Reveal({
  children,
  delayMs = 0,
  className = "",
}: {
  children: React.ReactNode;
  delayMs?: number;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const reduceMotion = useReducedMotion();
  const [shown, setShown] = useState(reduceMotion);

  useEffect(() => {
    if (reduceMotion) return;
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setShown(true);
          io.disconnect();
        }
      },
      // Fire a touch before the element is meaningfully on screen so the
      // rise reads as "arriving", not "late".
      { threshold: 0.1, rootMargin: "0px 0px -6% 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [reduceMotion]);

  return (
    <div
      ref={ref}
      className={`home-reveal ${shown ? "is-shown" : ""} ${className}`}
      style={delayMs ? { transitionDelay: `${delayMs}ms` } : undefined}
    >
      {children}
    </div>
  );
}

export function PageStyle() {
  return (
    <style>{`
      @keyframes homeRise {
        from { opacity: 0; transform: translateY(0.45em); }
        to { opacity: 1; transform: translateY(0); }
      }
      @keyframes homeFadeUp {
        from { opacity: 0; transform: translateY(24px); }
        to { opacity: 1; transform: translateY(0); }
      }
      @keyframes homePulse {
        0%, 100% { opacity: 1; transform: scale(1); }
        50% { opacity: 0.45; transform: scale(0.8); }
      }
      @keyframes homeScrollCue {
        0%, 100% { opacity: 0.25; transform: translateY(0); }
        50% { opacity: 0.9; transform: translateY(5px); }
      }
      @keyframes showcaseProgress {
        from { transform: scaleX(0); }
        to { transform: scaleX(1); }
      }
      @keyframes homeFloat {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(-9px); }
      }
      @keyframes homeCaret {
        0%, 45% { opacity: 1; }
        55%, 100% { opacity: 0; }
      }
      .home-rise > span { display: inline-block; animation: homeRise 0.9s cubic-bezier(0.16,1,0.3,1) both; }
      .home-fade { opacity: 0; animation: homeFadeUp 1s cubic-bezier(0.16,1,0.3,1) forwards; }
      .home-pulse { animation: homePulse 2.4s ease-in-out infinite; }
      .home-scroll-cue { animation: homeScrollCue 1.8s ease-in-out infinite; }
      .home-float { animation: homeFloat 7s ease-in-out infinite; }
      .home-caret { animation: homeCaret 1.05s step-end infinite; }
      .home-reveal {
        opacity: 0;
        transform: translateY(26px);
        transition: opacity 0.9s cubic-bezier(0.16,1,0.3,1), transform 0.9s cubic-bezier(0.16,1,0.3,1);
        will-change: opacity, transform;
      }
      .home-reveal.is-shown { opacity: 1; transform: translateY(0); }
      /* Brand text selection — background only, so ink stays ink on the bone
         sections and bone stays bone on noir. */
      .home-root ::selection { background: rgba(163,197,125,0.32); }
      /* Keyboard focus in the page aesthetic instead of the UA default ring. */
      .home-root :is(a, button, input):focus-visible {
        outline: 1px solid ${LEAF};
        outline-offset: 3px;
        border-radius: 2px;
      }
      @media (prefers-reduced-motion: reduce) {
        .home-rise > span, .home-fade { animation: none !important; opacity: 1 !important; transform: none !important; }
        .home-pulse, .home-scroll-cue, .home-float { animation: none !important; }
        .home-caret { animation: none !important; opacity: 1 !important; }
        .home-reveal { transition: none !important; opacity: 1 !important; transform: none !important; }
      }
    `}</style>
  );
}
