import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  FileText,
  Gavel,
  GraduationCap,
  Scale,
  Shield,
  Sparkles,
  Users,
} from "lucide-react";
import { ASH, BONE, DISPLAY, LINE_D, MATCHA } from "../theme";
import {
  InstrumentFrame,
  VBH,
  VBW,
  clampScore,
  curvePath,
  gridCellBorderStyle,
  riskBand,
  useCyclingIndex,
  useReducedMotion,
} from "./shared";

export const ER_INSIGHTS = [
  "Pattern detected: 3 escalating conflicts, Store 7 late shift.",
  "Suggested action: schedule mediation before Friday closeout.",
  "2 cases auto-categorized — severity confirmed by manager.",
];

// The subsystems the platform unifies — feeds the composite index, but also
// the point: one brain across every domain, not a single tool. Illustrative
// live counts.
export const PLATFORM_DOMAINS = [
  { icon: Shield, label: "IR · Safety", stat: "24 open", color: "#d9b65f" },
  { icon: Users, label: "Employee Rel.", stat: "8 cases", color: "#86efac" },
  { icon: Scale, label: "Compliance", stat: "6 juris.", color: "#E2725B" },
  { icon: Gavel, label: "Discipline", stat: "3 active", color: "#d9b65f" },
  { icon: GraduationCap, label: "Training", stat: "92%", color: "#86efac" },
  { icon: FileText, label: "Claims", stat: "2 open", color: "#7FB2C9" },
] as const;

export function PlatformInstrument() {
  const TARGET = 73;
  const reduce = useReducedMotion();
  const [score, setScore] = useState(reduce ? TARGET : 0);
  const [drawn, setDrawn] = useState(reduce ? 1 : 0);
  const [scanX, setScanX] = useState(-1);
  const [phase, setPhase] = useState(0);
  const raf = useRef(0);
  const start = useRef(0);
  const erIndex = useCyclingIndex(ER_INSIGHTS.length, 3200, reduce);

  useEffect(() => {
    if (reduce) return;
    const DUR = 1400;
    const SCAN = 3400;
    const loop = (now: number) => {
      if (!start.current) start.current = now;
      const e = now - start.current;
      const intro = Math.min(1, e / DUR);
      const eased = 1 - Math.pow(1 - intro, 3);
      setDrawn(eased);
      setPhase(e / 1100);
      const jitter = intro >= 1 ? Math.round(Math.sin(e / 650) * 1.4) : 0;
      setScore(Math.round(eased * TARGET) + jitter);
      setScanX((e % SCAN) / SCAN);
      raf.current = requestAnimationFrame(loop);
    };
    raf.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf.current);
  }, [reduce]);

  const { line, area } = curvePath(phase);
  const band = riskBand(score);
  const pathLen = VBW * 1.4;
  const ticks = [0.33, 0.66, 1];
  const subMetrics = [
    { label: "WC", value: clampScore(score - 6) },
    { label: "EPL", value: clampScore(score + 9) },
    { label: "ER", value: clampScore(score + 2) },
    { label: "COMPLIANCE", value: clampScore(score - 13) },
  ];

  return (
    <InstrumentFrame label="Composite Risk Index" accent={MATCHA}>
      {/* Two-column: left = the index + its loss curve + the AI layer,
          right = the per-domain breakdown, so the card fills its width.
          Stacks to one column below sm so nothing gets crushed on phones. */}
      <div className="grid grid-cols-1 sm:grid-cols-2 items-stretch">
      <div className="flex flex-col justify-between">
      <div className="px-5 pt-4 flex items-end justify-between">
        <span
          className="tabular-nums leading-none"
          style={{
            fontFamily: DISPLAY,
            fontWeight: 300,
            fontSize: "3.5rem",
            color: band.color,
          }}
        >
          {score}
          <span className="ml-1 align-top text-[0.9rem]" style={{ color: ASH }}>
            /100
          </span>
        </span>
        <div className="text-right">
          <div
            className="text-[11px] font-mono uppercase tracking-[0.2em]"
            style={{ color: band.color }}
          >
            {band.label}
          </div>
          <div
            className="text-[10px] font-mono uppercase tracking-[0.16em]"
            style={{ color: ASH }}
          >
            Modeled · updated live
          </div>
        </div>
      </div>
      <div className="px-3 pt-2">
        <svg
          viewBox={`0 0 ${VBW} ${VBH}`}
          preserveAspectRatio="none"
          className="w-full"
          style={{ height: 150 }}
        >
          <defs>
            <linearGradient id="homeRiskStroke" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#86efac" />
              <stop offset="44%" stopColor="#d9b65f" />
              <stop offset="100%" stopColor="#ce5a4f" />
            </linearGradient>
            <linearGradient id="homeRiskFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#d9b65f" stopOpacity="0.38" />
              <stop offset="100%" stopColor="#ce5a4f" stopOpacity="0" />
            </linearGradient>
          </defs>
          {ticks.map((f) => (
            <line
              key={f}
              x1={0}
              x2={VBW}
              y1={VBH - f * (VBH - 10)}
              y2={VBH - f * (VBH - 10)}
              stroke={LINE_D}
              strokeWidth={1}
              strokeDasharray={f === 1 ? "0" : "2 4"}
            />
          ))}
          <path d={area} fill="url(#homeRiskFill)" opacity={drawn} />
          <path
            d={line}
            fill="none"
            stroke="url(#homeRiskStroke)"
            strokeWidth={2}
            vectorEffect="non-scaling-stroke"
            strokeDasharray={pathLen}
            strokeDashoffset={pathLen * (1 - drawn)}
          />
          {scanX >= 0 && (
            <line
              x1={scanX * VBW}
              x2={scanX * VBW}
              y1={0}
              y2={VBH}
              stroke={MATCHA}
              strokeWidth={1.5}
              opacity={0.45}
            />
          )}
        </svg>
        <div
          className="flex justify-between mt-1 px-1 text-[9px] font-mono uppercase tracking-[0.16em]"
          style={{ color: ASH }}
        >
          <span>Low</span>
          <span>Risk trend →</span>
          <span>High</span>
        </div>
      </div>
      <div className="px-5 pt-3 pb-4">
        <div
          className="rounded-lg px-3.5 py-2.5 flex items-start gap-2.5"
          style={{
            border: `1px solid ${LINE_D}`,
            backgroundColor: "rgba(245,242,237,0.03)",
          }}
        >
          <Sparkles
            className="w-3.5 h-3.5 mt-0.5 shrink-0"
            style={{ color: MATCHA }}
          />
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 mb-1">
              <span
                className="text-[8px] font-mono uppercase tracking-[0.16em]"
                style={{ color: ASH }}
              >
                ER Copilot
              </span>
              <span
                className="home-pulse w-1 h-1 rounded-full"
                style={{ backgroundColor: MATCHA }}
              />
            </div>
            <AnimatePresence mode="wait">
              <motion.p
                key={erIndex}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.4 }}
                className="text-[11px] leading-snug"
                style={{ color: BONE }}
              >
                {ER_INSIGHTS[erIndex]}
              </motion.p>
            </AnimatePresence>
          </div>
        </div>
      </div>
      </div>
      {/* Right column — the sub-scores + every domain on one brain. Top
          border on mobile (stacked), left border once side-by-side. */}
      <div
        className="flex flex-col justify-between border-t sm:border-t-0 sm:border-l"
        style={{ borderColor: LINE_D }}
      >
      <div className="grid grid-cols-2 gap-x-3 gap-y-3 px-5 pb-4 pt-4">
        {subMetrics.map((m) => (
          <div key={m.label}>
            <div className="flex items-baseline justify-between mb-1.5">
              <span
                className="text-[8px] font-mono uppercase tracking-[0.12em]"
                style={{ color: ASH }}
              >
                {m.label}
              </span>
              <span
                className="text-[11px] font-mono tabular-nums"
                style={{ color: BONE }}
              >
                {m.value}
              </span>
            </div>
            <div
              className="h-[3px] rounded-full overflow-hidden"
              style={{ backgroundColor: LINE_D }}
            >
              <div
                className="h-full rounded-full transition-all duration-700"
                style={{
                  width: `${m.value}%`,
                  backgroundColor: riskBand(m.value).color,
                }}
              />
            </div>
          </div>
        ))}
      </div>
      {/* The breadth — every domain on one brain, not a single risk score.
          This is the platform's "much more than a number" story. */}
      <div className="px-5 pt-3 pb-4 border-t" style={{ borderColor: LINE_D }}>
        <div
          className="grid grid-cols-3 rounded-lg overflow-hidden border"
          style={{
            borderColor: LINE_D,
            backgroundColor: "rgba(245,242,237,0.02)",
          }}
        >
          {PLATFORM_DOMAINS.map((d, i) => {
            const Icon = d.icon;
            return (
              <div
                key={d.label}
                className="px-2.5 py-2"
                style={gridCellBorderStyle(i, PLATFORM_DOMAINS.length)}
              >
                <div className="flex items-center gap-1.5 mb-1">
                  <Icon
                    className="w-3 h-3 shrink-0"
                    style={{ color: d.color }}
                  />
                  <span
                    className="text-[8px] font-mono uppercase tracking-[0.1em] truncate"
                    style={{ color: ASH }}
                  >
                    {d.label}
                  </span>
                </div>
                <span
                  className="text-[12px] tabular-nums"
                  style={{ fontFamily: DISPLAY, fontWeight: 400, color: BONE }}
                >
                  {d.stat}
                </span>
              </div>
            );
          })}
        </div>
      </div>
      </div>
      </div>
      <div
        className="flex items-center justify-between px-5 pb-4 pt-3 border-t"
        style={{ borderColor: LINE_D }}
      >
        <span
          className="text-[9px] font-mono uppercase tracking-[0.16em]"
          style={{ color: ASH }}
        >
          One brain, every domain
        </span>
        <span
          className="text-[9px] font-mono uppercase tracking-[0.16em] shrink-0 ml-2"
          style={{ color: ASH }}
        >
          Unified
        </span>
      </div>
    </InstrumentFrame>
  );
}
