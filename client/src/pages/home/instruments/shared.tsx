import { useEffect, useRef, useState } from "react";
import { ASH, LINE_D } from "../theme";

export const RISK_BANDS = [
  { max: 39, label: "Exposed", color: "#ce5a4f" },
  { max: 59, label: "Developing", color: "#d98c4f" },
  { max: 79, label: "Adequate", color: "#d9b65f" },
  { max: 100, label: "Strong", color: "#86efac" },
] as const;

export function riskBand(score: number) {
  return (
    RISK_BANDS.find((b) => score <= b.max) ?? RISK_BANDS[RISK_BANDS.length - 1]
  );
}

export const CURVE_N = 48;

export function lognormal(x: number, mu = Math.log(0.32), sigma = 0.62) {
  const lnx = Math.log(Math.max(x, 0.001));
  return (
    Math.exp(-((lnx - mu) ** 2) / (2 * sigma * sigma)) /
    (x * sigma * Math.sqrt(2 * Math.PI))
  );
}

export const VBW = 320;
export const VBH = 110;

export function curveHeights(phase: number) {
  const mu = Math.log(0.3) + 0.12 * Math.sin(phase);
  const sigma = 0.6 + 0.08 * Math.sin(phase * 0.7 + 1);
  const raw = Array.from({ length: CURVE_N }, (_, i) =>
    lognormal((i + 0.5) / CURVE_N, mu, sigma),
  );
  const max = Math.max(...raw);
  return raw.map((v) => v / max);
}

export function curvePath(phase: number) {
  const pts = curveHeights(phase).map((h, i) => {
    const x = (i / (CURVE_N - 1)) * VBW;
    const y = VBH - h * (VBH - 10) - 4;
    return [x, y] as const;
  });
  const line = pts
    .map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`)
    .join(" ");
  const area = `${line} L${VBW},${VBH} L0,${VBH} Z`;
  return { line, area };
}

export function useReducedMotion() {
  return useRef(
    typeof window !== "undefined" &&
      !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches,
  ).current;
}

// Cycles 0..length-1 on an interval — used by the small "live AI" callouts
// (ER Copilot insight, voice-intake phase) so they feel alive without each
// instrument hand-rolling its own setInterval bookkeeping.
export function useCyclingIndex(length: number, intervalMs: number, reduce: boolean) {
  const [i, setI] = useState(0);
  useEffect(() => {
    if (reduce || length <= 1) return;
    const t = window.setInterval(
      () => setI((v) => (v + 1) % length),
      intervalMs,
    );
    return () => window.clearInterval(t);
  }, [length, intervalMs, reduce]);
  return i;
}

export function InstrumentFrame({
  label,
  accent,
  children,
}: {
  label: string;
  accent: string;
  children: React.ReactNode;
}) {
  return (
    <div className="relative home-float">
      {/* soft accent-tinted glow so the card reads as lifted off the black */}
      <div
        aria-hidden
        className="absolute -inset-x-6 -inset-y-4 pointer-events-none"
        style={{
          background: `radial-gradient(58% 60% at 50% 42%, ${accent}1f 0%, transparent 72%)`,
          filter: "blur(30px)",
        }}
      />
      <div
        className="relative w-full rounded-2xl backdrop-blur-sm"
        style={{
          border: "1px solid rgba(245,242,237,0.06)",
          backgroundColor: "rgba(245,242,237,0.025)",
          boxShadow:
            "inset 0 1px 0 rgba(255,255,255,0.05), 0 34px 64px -24px rgba(0,0,0,0.8), 0 12px 28px -14px rgba(0,0,0,0.55)",
        }}
      >
        <div
          className="flex items-center justify-between px-5 pt-4 pb-3 border-b"
          style={{ borderColor: "rgba(245,242,237,0.06)" }}
        >
          <span
            className="text-[10px] font-mono uppercase tracking-[0.22em]"
            style={{ color: ASH }}
          >
            {label}
          </span>
          <span
            className="inline-flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-[0.18em]"
            style={{ color: ASH }}
          >
            <span
              className="home-pulse w-1.5 h-1.5 rounded-full"
              style={{ backgroundColor: accent }}
            />
            Live
          </span>
        </div>
        {children}
      </div>
    </div>
  );
}

export function clampScore(n: number) {
  return Math.max(0, Math.min(100, n));
}

// Shared cell-divider style for the small stat grids (platform domains,
// compliance coverage) — one bordered grid with internal lines, not N
// separate floating boxes.
export function gridCellBorderStyle(i: number, total: number, cols = 3) {
  const rows = Math.ceil(total / cols);
  const isLastCol = i % cols === cols - 1;
  const isLastRow = i >= (rows - 1) * cols;
  return {
    borderRight: isLastCol ? undefined : `1px solid ${LINE_D}`,
    borderBottom: isLastRow ? undefined : `1px solid ${LINE_D}`,
  };
}
