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

export function PageStyle() {
  return (
    <style>{`
      @keyframes homeRise {
        from { opacity: 0; transform: translateY(0.45em); }
        to { opacity: 1; transform: translateY(0); }
      }
      @keyframes homeFadeUp {
        from { opacity: 0; transform: translateY(18px); }
        to { opacity: 1; transform: translateY(0); }
      }
      @keyframes homeMarquee {
        from { transform: translateX(0); }
        to { transform: translateX(-50%); }
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
      .home-rise > span { display: inline-block; animation: homeRise 0.9s cubic-bezier(0.16,1,0.3,1) both; }
      .home-fade { opacity: 0; animation: homeFadeUp 0.8s ease-out forwards; }
      .home-marquee-track { animation: homeMarquee 32s linear infinite; }
      .home-pulse { animation: homePulse 2.4s ease-in-out infinite; }
      .home-scroll-cue { animation: homeScrollCue 1.8s ease-in-out infinite; }
      .home-float { animation: homeFloat 7s ease-in-out infinite; }
      @media (prefers-reduced-motion: reduce) {
        .home-rise > span, .home-fade { animation: none !important; opacity: 1 !important; transform: none !important; }
        .home-marquee-track, .home-pulse, .home-scroll-cue, .home-float { animation: none !important; }
      }
    `}</style>
  );
}
