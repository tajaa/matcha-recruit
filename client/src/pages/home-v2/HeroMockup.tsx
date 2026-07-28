import { useEffect, useRef, useState } from "react";
import { motion, useInView } from "framer-motion";
import { Area, AreaChart, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { CREAM_HI, INK, INK_SOFT, MATCHA_LT, SANS } from "./theme";

// Ported from the retired /matcha-lite hero (components/landing/RiskInsightsHero.tsx,
// removed when Lite was rebuilt onto the noir surface) — the mock panel that
// MOVES continuously rather than stepping through states: the trend area chart
// scrolls + breathes a stacked hump on requestAnimationFrame, and the
// worker-comp posture numbers count up then live-jitter forever. Chrome
// recolored onto the home-v2 dark/amber tokens; severity colors stay
// semantic (red/amber/green), not brand.

const RED = "#C9614F";
const RED_DEEP = "#A84B3B";
const AMBER = MATCHA_LT;
const JADE = "#5FA87E";
const JADE_LITE = "#8FCBA6";
const LABEL = "rgba(239,234,224,0.4)";
const BORDER_SOFT = "rgba(239,234,224,0.08)";
const BORDER_HARD = "rgba(239,234,224,0.16)";

const TREND_POINTS = 26;
const TREND_LAYERS = [
  { key: "critical", color: RED_DEEP, amp: 6, spread: 4.5, phase: 0.0, breath: 0.9 },
  { key: "elevated", color: AMBER, amp: 9, spread: 5.5, phase: 0.6, breath: 1.4 },
  { key: "baseline", color: JADE, amp: 7, spread: 7.0, phase: 1.1, breath: 0.6 },
] as const;

function gaussian(x: number, center: number, spread: number) {
  const d = x - center;
  return Math.exp(-(d * d) / (2 * spread * spread));
}

function buildTrendFrame(t: number) {
  return Array.from({ length: TREND_POINTS }, (_, x) => {
    const row: Record<string, number> = { x };
    for (const layer of TREND_LAYERS) {
      const drift = (t * 0.085 + layer.phase) % 1;
      const c1 = drift * (TREND_POINTS + 8) - 4;
      const c2 = c1 - TREND_POINTS * 0.62;
      const breathe = 1 + Math.sin(t * layer.breath + layer.phase * 3) * 0.32;
      const amp = layer.amp * breathe;
      const v = amp * gaussian(x, c1, layer.spread) + amp * 0.5 * gaussian(x, c2, layer.spread * 0.9);
      row[layer.key] = Math.round(v * 10) / 10;
    }
    return row;
  });
}

function MovingTrend({ inView }: { inView: boolean }) {
  const [data, setData] = useState(() => buildTrendFrame(0));
  const rafRef = useRef(0);
  const lastRef = useRef(0);
  const startRef = useRef(0);

  useEffect(() => {
    if (!inView) return;
    const loop = (now: number) => {
      if (!startRef.current) startRef.current = now;
      if (now - lastRef.current > 42) {
        lastRef.current = now;
        setData(buildTrendFrame((now - startRef.current) / 1000));
      }
      rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafRef.current);
  }, [inView]);

  return (
    <div className="px-5 pt-4 pb-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[8px] uppercase tracking-widest font-bold flex items-center gap-2" style={{ color: LABEL }}>
          Incident Trend
          <span className="font-mono normal-case tracking-normal" style={{ color: RED }}>
            ↗ +429% recent vs prior half
          </span>
        </span>
        <div className="flex gap-1">
          {["BY SEVERITY", "90D"].map((l, i) => (
            <span
              key={l}
              className="px-1.5 py-0.5 rounded text-[7px] font-bold tracking-wider"
              style={{
                backgroundColor: i === 0 ? "rgba(239,234,224,0.08)" : "rgba(239,234,224,0.04)",
                color: i === 0 ? "rgba(239,234,224,0.88)" : LABEL,
                border: `1px solid ${BORDER_SOFT}`,
              }}
            >
              {l}
            </span>
          ))}
        </div>
      </div>
      <div style={{ height: 170 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 6, right: 0, bottom: 0, left: -28 }}>
            <defs>
              {TREND_LAYERS.map((l) => (
                <linearGradient key={l.key} id={`hv2rih-${l.key}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={l.color} stopOpacity={0.85} />
                  <stop offset="100%" stopColor={l.color} stopOpacity={0.25} />
                </linearGradient>
              ))}
            </defs>
            <XAxis dataKey="x" hide />
            <YAxis hide domain={[0, 34]} />
            {TREND_LAYERS.map((l) => (
              <Area
                key={l.key}
                type="monotone"
                dataKey={l.key}
                stackId="1"
                stroke={l.color}
                strokeWidth={1.25}
                fill={`url(#hv2rih-${l.key})`}
                isAnimationActive={false}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <div className="flex justify-between mt-1 text-[7px] font-mono" style={{ color: "rgba(239,234,224,0.28)" }}>
        {["Mar 15", "Apr 5", "Apr 26", "May 10", "May 24"].map((d) => (
          <span key={d}>{d}</span>
        ))}
      </div>
    </div>
  );
}

function useLiveMetric(
  target: number,
  run: boolean,
  { decimals = 0, jitter = 0, freq = 0.5, duration = 1400 }: { decimals?: number; jitter?: number; freq?: number; duration?: number },
) {
  const [val, setVal] = useState(0);
  const raf = useRef(0);
  const start = useRef(0);
  const last = useRef(0);
  useEffect(() => {
    if (!run) return;
    const tick = (now: number) => {
      if (!start.current) start.current = now;
      const elapsed = (now - start.current) / 1000;
      const t = Math.min(1, (now - start.current) / duration);
      let v: number;
      if (t < 1) {
        v = (1 - Math.pow(1 - t, 3)) * target;
      } else {
        v = target + Math.sin(elapsed * freq * 2 * Math.PI) * jitter + Math.sin(elapsed * freq * 3.3) * jitter * 0.45;
      }
      if (now - last.current > 50) {
        last.current = now;
        setVal(v);
      }
      raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [run, target, decimals, jitter, freq, duration]);
  return Math.max(0, val).toFixed(decimals);
}

function Sparkline({ run, color, freq }: { run: boolean; color: string; freq: number }) {
  const [pts, setPts] = useState<number[]>(() => Array(20).fill(0.5));
  const raf = useRef(0);
  const start = useRef(0);
  const last = useRef(0);
  useEffect(() => {
    if (!run) return;
    const tick = (now: number) => {
      if (!start.current) start.current = now;
      if (now - last.current > 90) {
        last.current = now;
        const t = (now - start.current) / 1000;
        setPts(
          Array.from({ length: 20 }, (_, i) => {
            const v = 0.5 + Math.sin(i * 0.5 + t * freq) * 0.32 + Math.sin(i * 0.9 - t * freq * 1.7) * 0.14;
            return Math.max(0.05, Math.min(0.95, v));
          }),
        );
      }
      raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [run, freq]);
  const d = pts.map((p, i) => `${i === 0 ? "M" : "L"}${(i / (pts.length - 1)) * 100},${(1 - p) * 24}`).join(" ");
  return (
    <svg viewBox="0 0 100 24" preserveAspectRatio="none" className="w-full h-5 mt-2" style={{ opacity: 0.7 }}>
      <path d={d} fill="none" stroke={color} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function WcCard({
  icon,
  label,
  value,
  sub,
  subColor,
  accent,
  freq,
  inView,
}: {
  icon: string;
  label: string;
  value: string;
  sub: string;
  subColor: string;
  accent: string;
  freq: number;
  inView: boolean;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={inView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.4 }}
      className="px-4 py-3.5 flex-1 min-w-0"
    >
      <div className="text-[7px] uppercase tracking-widest flex items-center gap-1 mb-2" style={{ color: LABEL }}>
        <span>{icon}</span>
        {label}
      </div>
      <div className="leading-none font-bold tabular-nums" style={{ fontSize: "1.5rem", color: RED, letterSpacing: "-0.02em" }}>
        {value}
      </div>
      <div className="text-[7px] mt-2 uppercase tracking-wider" style={{ color: subColor }}>
        {sub}
      </div>
      <Sparkline run={inView} color={accent} freq={freq} />
    </motion.div>
  );
}

function WcPosture({ inView }: { inView: boolean }) {
  const trir = useLiveMetric(66, inView, { decimals: 2, jitter: 1.4, freq: 0.45 });
  const dart = useLiveMetric(36, inView, { decimals: 2, jitter: 1.0, freq: 0.6 });
  const lost = useLiveMetric(326, inView, { decimals: 0, jitter: 4, freq: 0.3 });
  const streak = useLiveMetric(112, inView, { decimals: 0, jitter: 0, freq: 0.4, duration: 1700 });
  return (
    <div className="border-t" style={{ borderColor: BORDER_SOFT }}>
      <div className="px-5 pt-3 pb-1 text-[8px] uppercase tracking-widest" style={{ color: LABEL }}>
        ♡ Workers Comp Posture · Trailing 12 mo
      </div>
      <div className="flex divide-x" style={{ borderColor: BORDER_SOFT }}>
        <WcCard icon="∿" label="TRIR" value={trir} sub="1733% above median" subColor={RED_DEEP} accent={RED} freq={0.9} inView={inView} />
        <WcCard icon="∿" label="DART" value={dart} sub="1700% above median" subColor={RED_DEEP} accent={AMBER} freq={1.2} inView={inView} />
        <WcCard icon="▦" label="Lost Days" value={lost} sub="+10 restricted" subColor={LABEL} accent="rgba(239,234,224,0.5)" freq={0.6} inView={inView} />
        <WcCard icon="♡" label="Claims-free" value={streak} sub="days" subColor={LABEL} accent={JADE} freq={0.8} inView={inView} />
      </div>
    </div>
  );
}

export function HeroMockup() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { margin: "-60px" });

  return (
    <div
      ref={ref}
      className="rounded-xl overflow-x-auto border"
      style={{ borderColor: BORDER_HARD, backgroundColor: CREAM_HI, fontFamily: SANS }}
    >
      <div className="min-w-[480px]">
        <div className="flex items-center justify-between px-5 py-3.5 border-b" style={{ borderColor: BORDER_SOFT }}>
          <div className="flex items-center gap-2">
            <span className="text-sm font-bold" style={{ color: INK }}>
              Risk Insights
            </span>
            <motion.span
              className="px-1.5 py-0.5 rounded text-[8px] font-medium"
              style={{ backgroundColor: "rgba(95,168,126,0.15)", color: JADE_LITE, border: "1px solid rgba(95,168,126,0.3)" }}
              animate={inView ? { opacity: [1, 0.45, 1] } : {}}
              transition={{ duration: 1.8, repeat: Infinity, ease: "easeInOut" }}
            >
              LIVE
            </motion.span>
          </div>
          <div className="flex items-center gap-1.5">
            {(["All locations", "Last 90 days"] as const).map((label) => (
              <div
                key={label}
                className="flex items-center gap-1 px-2 py-1 rounded"
                style={{ backgroundColor: "rgba(239,234,224,0.04)", border: `1px solid ${BORDER_SOFT}`, color: INK_SOFT, fontSize: 8 }}
              >
                {label} <span style={{ fontSize: 7 }}>▾</span>
              </div>
            ))}
          </div>
        </div>
        <MovingTrend inView={inView} />
        <WcPosture inView={inView} />
      </div>
    </div>
  );
}
