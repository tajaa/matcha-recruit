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
      /* Hero entrance. 0.42s, not the 1s .home-fade: the hero's elements are
         staggered 60/140/240ms apart and a 1s fade meant the conversion element
         wasn't fully opaque until 3.3s. Everything settles under 700ms now. */
      .home-fade-fast { opacity: 0; animation: homeFadeUp 0.42s cubic-bezier(0.16,1,0.3,1) forwards; }
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
      /* iOS Safari paints a translucent grey box over any tapped link/button.
         On a noir editorial surface it reads as a rendering fault, and every
         control here already has its own :active/hover treatment. */
      .home-root a, .home-root button, .home-root input, .home-root summary {
        -webkit-tap-highlight-color: transparent;
      }
      /* Short landscape — a phone rotated. The hero's stacked deck row is
         taller than the viewport there, which pushed the email capture (the
         page's one conversion point) fully below the fold: 364px of content in
         a 340px viewport on an iPhone 12. Compress the fold rather than let the
         conversion element fall off it. Height-keyed, not width-keyed, so a
         landscape tablet with real height keeps the normal layout. */
      @media (orientation: landscape) and (max-height: 520px) {
        .home-hero { min-height: 0; }
        .home-hero-body { padding-top: 82px; padding-bottom: 20px; }
        .home-hero h1 { font-size: clamp(1.5rem, 3.6vw, 2.5rem); }
        .home-hero-deck {
          margin-top: 1.25rem;
          flex-direction: row;
          align-items: flex-end;
          justify-content: space-between;
          gap: 2rem;
        }
        .home-hero-deck > p { font-size: 1.05rem; }
        .home-hero-capture { width: 330px; flex-shrink: 0; }
        /* Supplementary, and the fold has no room for it rotated. */
        .home-hero-proof, .home-root .home-scroll-cue { display: none; }
      }
      /* Keyboard focus in the page aesthetic instead of the UA default ring. */
      .home-root :is(a, button, input):focus-visible {
        outline: 1px solid ${LEAF};
        outline-offset: 3px;
        border-radius: 2px;
      }
      @media (prefers-reduced-motion: reduce) {
        .home-rise > span, .home-fade, .home-fade-fast { animation: none !important; opacity: 1 !important; transform: none !important; }
        .home-pulse, .home-scroll-cue, .home-float { animation: none !important; }
        .home-caret { animation: none !important; opacity: 1 !important; }
        .home-reveal { transition: none !important; opacity: 1 !important; transform: none !important; }
      }
    `}</style>
  );
}
