// Light-tuned twin of pages/home/PageChrome.tsx:GrainOverlay — same asset,
// different blend. `soft-light` at 0.05 (the noir tuning) washes out on a
// light ground; `multiply` at a much lower opacity gives cream some tooth
// without dirtying the white.
export function PaperGrain() {
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-0 z-[60]"
      style={{
        backgroundImage: "url('/textures/asfalt-light.png')",
        backgroundRepeat: "repeat",
        opacity: 0.035,
        mixBlendMode: "multiply",
      }}
    />
  );
}
