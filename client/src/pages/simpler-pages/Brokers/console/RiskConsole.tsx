import { useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Settings } from "lucide-react";
import { CHASSIS, CRITICAL, GLASS, LEAF, AMBER, ROOM_MUTED, ROOM_TEXT } from "./materials";
import { Fader, Knob, Lcd, Led, ModulePanel, TubeTile, WaveTile } from "./parts";
import { VBH, VBW, curvePath, useReducedMotion } from "../../../home/instruments/shared";
import { BAND_COLOR, RADAR_ROWS } from "../data";

const AXIS_LABELS = ["10k", "25k", "50k", "100k", "250k", "500k"];

// Deterministic per-client spike heights behind the two distribution curves —
// not random per render (would make headless screenshots non-reproducible),
// just a fixed illustrative spectrum.
const SPIKES = [0.18, 0.32, 0.5, 0.28, 0.62, 0.4, 0.78, 0.55, 0.9, 0.5, 0.72, 0.35, 0.6, 0.42, 0.25];

const flaggedCount = RADAR_ROWS.filter((r) => r.band !== "stable").length;

function GlassDisplay() {
  const reduceMotion = useReducedMotion();
  const [phase, setPhase] = useState(0);
  const rafRef = useRef(0);
  const lastRef = useRef(0);

  useEffect(() => {
    if (reduceMotion) return;
    const FPS = 8;
    const step = (now: number) => {
      if (now - lastRef.current > 1000 / FPS) {
        lastRef.current = now;
        setPhase((p) => p + 0.045);
      }
      rafRef.current = requestAnimationFrame(step);
    };
    rafRef.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(rafRef.current);
  }, [reduceMotion]);

  const current = curvePath(phase);
  const prior = curvePath(phase + 1.15);
  const spikeW = VBW / SPIKES.length;

  return (
    <div className="relative overflow-hidden" style={{ ...GLASS, height: 168 }}>
      <div className="absolute inset-x-0 top-0 flex items-center justify-between px-4 pt-3">
        <span className="text-[9px] font-mono uppercase tracking-[0.16em]" style={{ color: ROOM_MUTED }}>
          Book risk curve
        </span>
        <span className="text-[9px] font-mono uppercase tracking-[0.16em] flex items-center gap-1.5" style={{ color: ROOM_MUTED }}>
          <Led color={LEAF} size={5} pulse /> live
        </span>
      </div>

      <span
        className="absolute left-1/2 top-[38%] -translate-x-1/2 -translate-y-1/2 select-none pointer-events-none text-[13px] font-semibold tracking-[0.3em] uppercase"
        style={{ color: "rgba(237,239,243,0.16)" }}
      >
        Risk Engine
      </span>

      <svg viewBox={`0 0 ${VBW} ${VBH}`} preserveAspectRatio="none" className="absolute inset-x-0 bottom-6 top-9 w-full h-[calc(100%-56px)]">
        <defs>
          <linearGradient id="curveLeaf" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={LEAF} stopOpacity={0.5} />
            <stop offset="100%" stopColor={LEAF} stopOpacity={0} />
          </linearGradient>
          <linearGradient id="curveAmber" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={AMBER} stopOpacity={0.4} />
            <stop offset="100%" stopColor={AMBER} stopOpacity={0} />
          </linearGradient>
        </defs>

        {SPIKES.map((h, i) => (
          <rect
            key={i}
            x={i * spikeW + spikeW * 0.28}
            width={spikeW * 0.44}
            y={VBH - h * (VBH - 8)}
            height={h * (VBH - 8)}
            fill="rgba(237,239,243,0.08)"
          />
        ))}

        <path d={prior.area} fill="url(#curveAmber)" />
        <path
          d={prior.line}
          fill="none"
          stroke={AMBER}
          strokeWidth={1.25}
          strokeOpacity={0.85}
          style={{ filter: `drop-shadow(0 0 4px ${AMBER}99)` }}
        />
        <path d={current.area} fill="url(#curveLeaf)" />
        <path
          d={current.line}
          fill="none"
          stroke={LEAF}
          strokeWidth={1.5}
          style={{ filter: `drop-shadow(0 0 5px ${LEAF}bb)` }}
        />
      </svg>

      <div className="absolute inset-x-0 bottom-0 flex items-center justify-between px-4 pb-2.5">
        {AXIS_LABELS.map((l) => (
          <span key={l} className="text-[8px] font-mono tabular-nums" style={{ color: "rgba(237,239,243,0.28)" }}>
            {l}
          </span>
        ))}
      </div>
    </div>
  );
}

/**
 * Decorative "Book Risk Console" — a skeuomorphic instrument replacing the
 * flat BookRiskCurveCard list. Purely illustrative (RADAR_ROWS/BAND_COLOR
 * still drive the flagged count so it stays tied to the same book the rest
 * of the page describes); marked aria-hidden since the hero's real content
 * is the text column beside it.
 */
export function RiskConsole() {
  return (
    <div aria-hidden="true" className="w-full p-4 sm:p-5" style={CHASSIS}>
      <style>{`
        @keyframes consoleLedPulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }
        .console-led-pulse { animation: consoleLedPulse 2.4s ease-in-out infinite; }
        @media (prefers-reduced-motion: reduce) {
          .console-led-pulse { animation: none !important; opacity: 1 !important; }
        }
      `}</style>

      {/* Top strip */}
      <div className="flex items-center justify-between px-1.5 pb-4">
        <span className="text-[13px] font-semibold tracking-[0.08em]" style={{ color: ROOM_TEXT }}>
          MATCHA
        </span>
        <div
          className="flex items-center gap-3 px-4 py-1.5 rounded-full text-[11px] font-mono"
          style={{ ...GLASS, color: ROOM_MUTED }}
        >
          <ArrowUp className="w-3 h-3 opacity-50" />
          <span>Book · 24 clients</span>
          <ArrowDown className="w-3 h-3 opacity-50" />
        </div>
        <div className="flex items-center gap-2.5" style={{ color: ROOM_MUTED }}>
          <ChevronLeft className="w-3.5 h-3.5 opacity-50" />
          <ChevronRight className="w-3.5 h-3.5 opacity-50" />
          <Settings className="w-3.5 h-3.5 opacity-50 ml-1.5" />
        </div>
      </div>

      <GlassDisplay />

      {/* Module rack */}
      <div className="flex items-stretch gap-2.5 mt-3">
        <Fader value={0.62} accent={LEAF} height={128} />

        <ModulePanel label="TRIR" accent={LEAF}>
          <div className="flex items-center gap-3">
            <Knob value={0.4} accent={LEAF} size={48} />
            <Lcd label="Avg" value="2.8" accent={LEAF} />
          </div>
        </ModulePanel>

        <ModulePanel label="DART" accent={AMBER}>
          <div className="flex items-center gap-3">
            <Knob value={0.55} accent={AMBER} size={48} />
            <Lcd label="Avg" value="1.4" accent={AMBER} />
          </div>
        </ModulePanel>

        <ModulePanel label="Loss control" accent={LEAF}>
          <div className="flex items-center gap-3">
            <Knob value={0.7} accent={LEAF} size={40} />
            <TubeTile accent={LEAF} />
          </div>
        </ModulePanel>

        <ModulePanel label="Outreach" accent={CRITICAL}>
          <div className="flex items-center gap-3">
            <Knob value={0.3} accent={CRITICAL} size={40} />
            <WaveTile accent={CRITICAL} />
          </div>
        </ModulePanel>

        <Fader value={0.38} accent={AMBER} height={128} />
      </div>

      {/* Footer strip */}
      <div className="flex items-center justify-between px-1.5 pt-4">
        <span className="text-[9px] font-mono uppercase tracking-[0.16em]" style={{ color: ROOM_MUTED }}>
          Updated from client intake
        </span>
        <div className="flex items-center gap-1.5">
          {(["critical", "elevated", "stable"] as const).map((band) => (
            <span key={band} className="flex items-center gap-1 px-2 py-1 rounded-full" style={GLASS}>
              <Led color={BAND_COLOR[band]} size={5} />
              <span className="text-[9px] font-mono uppercase tracking-wider" style={{ color: ROOM_MUTED }}>
                {band}
              </span>
            </span>
          ))}
        </div>
        <span className="text-[9px] font-mono uppercase tracking-[0.16em]" style={{ color: ROOM_MUTED }}>
          {flaggedCount} of 24 flagged
        </span>
      </div>
    </div>
  );
}
