import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { AnimatePresence, motion, MotionConfig } from "framer-motion";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  FileText,
  Gavel,
  GraduationCap,
  Loader2,
  Lock,
  Mic,
  Scale,
  Shield,
  Sparkles,
  Users,
} from "lucide-react";

import MarketingNav from "./landing/MarketingNav";
import MarketingFooter from "./landing/MarketingFooter";
import { PricingContactModal } from "../components/PricingContactModal";
import { useSEO } from "../hooks/useSEO";

// ---------------------------------------------------------------------------
// Palette — editorial / culture-brand. Near-black canvas, bone type, electric
// matcha accent. Deliberately NOT the ivory product-page system; this is the
// brand front door.
// ---------------------------------------------------------------------------

const NOIR = "#0E0E0C";
const BONE = "#F5F2ED";
const ASH = "#8F8B80";
const MATCHA = "#F5F2ED";
const LINE_D = "rgba(245,242,237,0.14)";
const DISPLAY = "var(--font-display)"; // Fraunces

type Product = {
  n: string;
  name: string;
  subheader?: string;
  nameSize?: string;
  blurb: string;
  to: string;
  accent: string;
};

// 2×2 in spirit (software / people) but presented as a stacked editorial index.
const PRODUCTS: Product[] = [
  {
    n: "01",
    name: "Full Platform",
    subheader: "Full Risk and Employee Relations Suite",
    blurb:
      "Agentic risk management — safety, compliance, and employee relations on one brain.",
    to: "/matcha-platform",
    accent: "#F5F2ED",
  },
  {
    n: "02",
    name: "Matcha Lite",
    subheader: "Incident Reporting and OSHA Logs",
    blurb:
      "Incident reporting, OSHA 300 logs, and a full HR library. Bundled for small teams.",
    to: "/matcha-lite",
    accent: "#F2C14E",
  },
  {
    n: "03",
    name: "Compliance",
    subheader: "Multi-State Jurisdictional Intelligence",
    blurb:
      "Multi-state regulatory tracking, jurisdiction-aware alerts, and audit-ready records.",
    to: "/matcha-compliance",
    accent: "#E2725B",
  },
  {
    n: "04",
    name: "Consulting",
    blurb:
      "Bespoke HR, governance, and employee-relations counsel. Senior practitioners, in the room.",
    to: "/services",
    accent: "#7FB2C9",
  },
];

// Hero carousel slides. Not 1:1 with PRODUCTS: Matcha Lite gets two slides
// (the incident-reporting flow + its OSHA 300 recordkeeping), both keyed "02"
// and titled "Matcha Lite" with the same subheader — the OSHA facet is part
// of the Matcha Lite bundle, not a separate product, so it shouldn't read as
// one. Routed to /matcha-daily so they read as two facets of one product.
// Order is presentation, not the product numbering: lead with the entry-tier
// product (Matcha Lite, then its OSHA facet), then Compliance, then close on
// the Full Platform as the "and everything above, unified" capstone.
// Consulting is people, not an instrument, and stays text-only in the index below.
const CAROUSEL_PRODUCTS: Product[] = [
  {
    n: "02",
    name: "Matcha Lite: Incident Reporting Pro",
    blurb:
      "Incident reporting, OSHA 300 logs, and a full HR library. Bundled for small teams.",
    to: "/matcha-lite",
    accent: "#F2C14E",
  },
  {
    n: "02",
    name: "Matcha Lite: 1 Click OSHA Logs Export",
    nameSize: "clamp(1.35rem, 1.85vw, 2.1rem)",
    blurb:
      "Recordable incidents flow straight into your OSHA 300 log, 300A summary, and ITA export.",
    to: "/matcha-lite",
    accent: "#F2C14E",
  },
  PRODUCTS[2], // 03 Compliance
  PRODUCTS[0], // 01 Full Platform
];

const MARQUEE_WORDS = [
  "WORKPLACE SAFETY",
  "COMPLIANCE",
  "EMPLOYEE RELATIONS",
  "RISK MANAGEMENT",
  "PEOPLE STRATEGY",
  "REGULATORY TRACKING",
];

const HOME_JSON_LD = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: "Matcha",
  url: "https://hey-matcha.com/",
  description:
    "Full-service HR — an agentic risk & compliance platform, Matcha Lite for small teams, multi-state compliance tracking, and senior advisory.",
  makesOffer: [
    {
      "@type": "Offer",
      itemOffered: {
        "@type": "Service",
        name: "HR Risk & Compliance Platform",
      },
    },
    {
      "@type": "Offer",
      itemOffered: {
        "@type": "Service",
        name: "Matcha Lite — Incident Reporting & HR Records",
      },
    },
    {
      "@type": "Offer",
      itemOffered: {
        "@type": "Service",
        name: "Compliance — Multi-State Regulatory Tracking",
      },
    },
    {
      "@type": "Offer",
      itemOffered: { "@type": "Service", name: "HR & Compliance Consulting" },
    },
  ],
};

export default function Home() {
  const [isPricingOpen, setIsPricingOpen] = useState(false);

  useSEO({
    title: "Matcha — Full-Service HR: Platform, Lite, Compliance & Consulting",
    description:
      "Full-service HR for modern companies — an agentic risk & compliance platform, Matcha Lite for small teams, multi-state compliance tracking, and senior advisory. One standard of rigor across software and people.",
    canonical: "https://hey-matcha.com/",
    jsonLd: HOME_JSON_LD,
  });

  return (
    <div
      style={{ backgroundColor: NOIR, color: BONE }}
      className="min-h-screen overflow-x-hidden"
    >
      <PageStyle />
      <GrainOverlay />

      <PricingContactModal
        isOpen={isPricingOpen}
        onClose={() => setIsPricingOpen(false)}
      />
      <MarketingNav onDemoClick={() => setIsPricingOpen(true)} />

      <Hero />
      <ProductIndex />
      <Manifesto />
      <CTABand onDemoClick={() => setIsPricingOpen(true)} />

      <div style={{ backgroundColor: BONE, color: "var(--color-ivory-ink)" }}>
        <MarketingFooter newsletterVariant="matcha" />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Grain + keyframes
// ---------------------------------------------------------------------------

function GrainOverlay() {
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

function PageStyle() {
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

// ---------------------------------------------------------------------------
// Hero — magazine cover
// ---------------------------------------------------------------------------

function Hero() {
  return (
    <section className="relative w-full min-h-[100svh] flex flex-col">
      {/* Masthead row */}
      <div className="max-w-[1600px] mx-auto w-full px-6 sm:px-10 pt-[76px] sm:pt-[84px]">
        <div className="home-fade" style={{ animationDelay: "0.05s" }}>
          <div className="grid grid-cols-2 sm:grid-cols-3 items-center pb-3">
            <span
              className="flex items-center gap-2.5 text-[10.5px] tracking-[0.28em] font-mono uppercase"
              style={{ color: ASH }}
            >
              <span
                className="w-1 h-1 rounded-full shrink-0"
                style={{ backgroundColor: "#A3C57D" }}
              />
              Managing your risk
            </span>
            <span
              className="hidden sm:block justify-self-center text-[10.5px] tracking-[0.28em] font-mono uppercase"
              style={{ color: ASH }}
            >
              Software · Practitioners
            </span>
            <span
              className="justify-self-end text-[10.5px] tracking-[0.28em] font-mono uppercase tabular-nums"
              style={{ color: ASH }}
            >
              Vol. 01
            </span>
          </div>
          {/* magazine folio — double hairline under the masthead row */}
          <div style={{ height: 1, backgroundColor: LINE_D }} />
          <div
            className="mt-[3px]"
            style={{ height: 1, backgroundColor: LINE_D, opacity: 0.45 }}
          />
        </div>
      </div>

      {/* Ticker — pulled high so it reads immediately, no scroll required */}
      <div>
        <Marquee />
      </div>

      {/* Headline + supporting content, stacked at every breakpoint — the
          carousel sits full-width below the headline/CTAs instead of
          fighting them for space in a side-by-side column. */}
      <div className="relative max-w-[1600px] mx-auto w-full px-6 sm:px-10 flex-1 flex flex-col justify-center py-8 sm:py-10">
        <div>
          <div>
            <h1
              className="home-rise tracking-[-0.02em] text-[clamp(2.2rem,7vw,6.5rem)] xl:text-[clamp(2.4rem,4.7vw,4.7rem)]"
              style={{ fontFamily: DISPLAY, fontWeight: 300, lineHeight: 1.02 }}
            >
              <span style={{ animationDelay: "0.16s" }}>We run the whole</span>{" "}
              <span
                style={{
                  animationDelay: "0.36s",
                  color: "#D97706",
                  fontStyle: "italic",
                }}
              >
                risk
              </span>
              <span style={{ animationDelay: "0.44s" }}>&nbsp;&amp;&nbsp;</span>
              <span
                style={{
                  animationDelay: "0.54s",
                  color: MATCHA,
                  fontStyle: "italic",
                }}
              >
                people
              </span>
              <span style={{ animationDelay: "0.62s" }}>&nbsp;function.</span>
            </h1>

            {/* Deck row — editorial band under the headline: hairline rule,
                tagline left, the starting-line cue right as a circled arrow. */}
            <div
              className="mt-10 pt-7 border-t flex flex-col lg:flex-row lg:items-end lg:justify-between gap-8 home-fade"
              style={{ borderColor: LINE_D, animationDelay: "0.66s" }}
            >
              <p
                className="max-w-3xl text-xl sm:text-2xl"
                style={{ color: BONE, lineHeight: 1.5 }}
              >
                <span style={{ color: "#FFFFFF" }}>
                  Managing your risk before your risk manages you.
                </span>{" "}
                <span style={{ color: ASH }}>
                  Workplace safety, compliance, and risk analysis.
                </span>
              </p>
              <a
                href="#index"
                className="group inline-flex items-center gap-3.5 shrink-0 pb-1"
              >
                <span
                  className="text-[11px] font-mono uppercase tracking-[0.22em] transition-colors duration-200"
                  style={{ color: BONE }}
                >
                  Find your starting line
                </span>
                <span
                  aria-hidden
                  className="flex items-center justify-center w-9 h-9 rounded-full border transition-colors duration-200 group-hover:bg-[#A3C57D] group-hover:border-[#A3C57D] group-hover:text-[#0E0E0C]"
                  style={{ borderColor: LINE_D, color: ASH }}
                >
                  ↓
                </span>
              </a>
            </div>
          </div>

          <div
            className="mt-14 home-fade w-full max-w-[1360px] mx-auto"
            style={{ animationDelay: "0.8s" }}
          >
            <ProductCarousel />
          </div>
        </div>
      </div>

      {/* Scroll cue — blinking chevron so it reads as "there's more below" */}
      <a
        href="#index"
        aria-label="Scroll to products"
        className="home-scroll-cue absolute bottom-5 left-1/2 -translate-x-1/2 z-10 hover:opacity-100"
        style={{ color: ASH }}
      >
        <ChevronDown className="w-6 h-6" strokeWidth={1.5} />
      </a>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Marquee
// ---------------------------------------------------------------------------

function Marquee() {
  const row = [...MARQUEE_WORDS, ...MARQUEE_WORDS];
  return (
    <div
      className="relative overflow-hidden border-y py-[5px] select-none"
      style={{ borderColor: LINE_D, backgroundColor: MATCHA }}
    >
      <div className="home-marquee-track flex w-max items-center whitespace-nowrap">
        {row.map((w, i) => (
          <span key={i} className="flex items-center">
            <span
              className="px-4 text-[clamp(0.5rem,0.85vw,0.78rem)] tracking-tight"
              style={{ fontFamily: DISPLAY, fontWeight: 400, color: "#5C584E" }}
            >
              {w}
            </span>
            <span className="text-[0.5rem]" style={{ color: "#5C584E" }}>
              ✦
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Instrument carousel — bespoke "instrument" graphics in the hero's own
// palette (noir/bone/Fraunces), not the real product pages' dense dashboards
// scaled down. Each is self-contained SVG/CSS + a count-up, same restrained
// language as the rest of the hero. Autoplays (paused on hover), dots only —
// floats in the same hero as the headline, not a separate section.
// ---------------------------------------------------------------------------

const RISK_BANDS = [
  { max: 39, label: "Exposed", color: "#ce5a4f" },
  { max: 59, label: "Developing", color: "#d98c4f" },
  { max: 79, label: "Adequate", color: "#d9b65f" },
  { max: 100, label: "Strong", color: "#86efac" },
] as const;

function riskBand(score: number) {
  return (
    RISK_BANDS.find((b) => score <= b.max) ?? RISK_BANDS[RISK_BANDS.length - 1]
  );
}

const CURVE_N = 48;

function lognormal(x: number, mu = Math.log(0.32), sigma = 0.62) {
  const lnx = Math.log(Math.max(x, 0.001));
  return (
    Math.exp(-((lnx - mu) ** 2) / (2 * sigma * sigma)) /
    (x * sigma * Math.sqrt(2 * Math.PI))
  );
}

const VBW = 320;
const VBH = 110;

function curveHeights(phase: number) {
  const mu = Math.log(0.3) + 0.12 * Math.sin(phase);
  const sigma = 0.6 + 0.08 * Math.sin(phase * 0.7 + 1);
  const raw = Array.from({ length: CURVE_N }, (_, i) =>
    lognormal((i + 0.5) / CURVE_N, mu, sigma),
  );
  const max = Math.max(...raw);
  return raw.map((v) => v / max);
}

function curvePath(phase: number) {
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

function useReducedMotion() {
  return useRef(
    typeof window !== "undefined" &&
      !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches,
  ).current;
}

// Cycles 0..length-1 on an interval — used by the small "live AI" callouts
// (ER Copilot insight, voice-intake phase) so they feel alive without each
// instrument hand-rolling its own setInterval bookkeeping.
function useCyclingIndex(length: number, intervalMs: number, reduce: boolean) {
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

function InstrumentFrame({
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

function clampScore(n: number) {
  return Math.max(0, Math.min(100, n));
}

// Shared cell-divider style for the small stat grids (platform domains,
// compliance coverage) — one bordered grid with internal lines, not N
// separate floating boxes.
function gridCellBorderStyle(i: number, total: number, cols = 3) {
  const rows = Math.ceil(total / cols);
  const isLastCol = i % cols === cols - 1;
  const isLastRow = i >= (rows - 1) * cols;
  return {
    borderRight: isLastCol ? undefined : `1px solid ${LINE_D}`,
    borderBottom: isLastRow ? undefined : `1px solid ${LINE_D}`,
  };
}

const ER_INSIGHTS = [
  "Pattern detected: 3 escalating conflicts, Store 7 late shift.",
  "Suggested action: schedule mediation before Friday closeout.",
  "2 cases auto-categorized — severity confirmed by manager.",
];

// The subsystems the platform unifies — feeds the composite index, but also
// the point: one brain across every domain, not a single tool. Illustrative
// live counts.
const PLATFORM_DOMAINS = [
  { icon: Shield, label: "IR · Safety", stat: "24 open", color: "#d9b65f" },
  { icon: Users, label: "Employee Rel.", stat: "8 cases", color: "#86efac" },
  { icon: Scale, label: "Compliance", stat: "6 juris.", color: "#E2725B" },
  { icon: Gavel, label: "Discipline", stat: "3 active", color: "#d9b65f" },
  { icon: GraduationCap, label: "Training", stat: "92%", color: "#86efac" },
  { icon: FileText, label: "Claims", stat: "2 open", color: "#7FB2C9" },
] as const;

function PlatformInstrument() {
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
  const pMarkers = [
    { f: 0.18, l: "P50" },
    { f: 0.46, l: "P90" },
    { f: 0.74, l: "P99" },
  ];
  const subMetrics = [
    { label: "WC", value: clampScore(score - 6) },
    { label: "EPL", value: clampScore(score + 9) },
    { label: "ER", value: clampScore(score + 2) },
    { label: "COMPLIANCE", value: clampScore(score - 13) },
  ];

  return (
    <InstrumentFrame label="Composite Risk Index" accent={MATCHA}>
      {/* Two-column: left = the index + its loss curve + the AI layer,
          right = the per-domain breakdown, so the card fills its width. */}
      <div className="grid grid-cols-2 items-stretch">
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
          {pMarkers.map((m) => (
            <g key={m.l} opacity={0.6 * drawn}>
              <line
                x1={m.f * VBW}
                x2={m.f * VBW}
                y1={8}
                y2={VBH}
                stroke={BONE}
                strokeOpacity={0.22}
                strokeWidth={1}
                strokeDasharray="2 3"
              />
              <text
                x={m.f * VBW + 3}
                y={16}
                fontSize={7}
                fontFamily="monospace"
                fill={ASH}
                letterSpacing={0.5}
              >
                {m.l}
              </text>
            </g>
          ))}
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
          <span>$0</span>
          <span>Annual loss exposure →</span>
          <span>PML</span>
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
      {/* Right column — the sub-scores + every domain on one brain. */}
      <div
        className="flex flex-col justify-between border-l"
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

const DAILY_BARS = [3, 5, 2, 6, 4, 1, 4]; // Mon..Sun total — illustrative
const DAILY_LABELS = ["M", "T", "W", "T", "F", "S", "S"];
// Illustrative category split per day — communicates the AI categorization,
// not just a raw count.
const DAILY_BEHAVIORAL_PCT = DAILY_BARS.map((v) =>
  Math.round((Math.round(v * 0.6) / v) * 100),
);

// Illustrative waveform shape (not real audio) for the voice-intake demo —
// the magic link's "Dictate" button is a real shipped feature (see
// adminUpdates.ts "ir-magic-link-voice"), this animates what it looks like.
const VOICE_WAVEFORM = [
  0.3, 0.6, 0.85, 0.5, 0.95, 0.4, 0.7, 0.55, 0.9, 0.35, 0.65, 0.45,
];
// 0-2 are plain status text; phase 3 ("extracted") renders structured
// fields instead of a string — see the voicePhase === 3 branch below.
const VOICE_STATUS = ["Tap to dictate", "Listening…", "Transcribing…"];
const VOICE_PHASE_COUNT = 4;

// Actual logged records (illustrative) + their AI analytics — a taste of the
// incident log itself, not just the intake form. Each row: location, type,
// auto-categorized class, severity.
const RECENT_INCIDENTS = [
  {
    loc: "Atlanta — Store 7",
    type: "Customer escalation",
    sev: "High",
    color: "#ce5a4f",
  },
  {
    loc: "Phoenix — Warehouse",
    type: "Slip / fall",
    sev: "Med",
    color: "#F2C14E",
  },
  { loc: "Dallas — Store 3", type: "Near-miss", sev: "Low", color: "#86efac" },
];

// One report opened with its agentic analysis — the "report itself + its
// data", not just the intake. Illustrative. Index here doubles as the
// "field" a NARRATIVE_TOKENS chunk points at (see below) — same order,
// same meaning, so the highlighted phrase and the resolved fact always match.
const REPORT_ANALYSIS = [
  { label: "Pattern", value: "3rd escalation · this location · 14 days" },
  { label: "Policy", value: "Workplace Violence Prevention §4" },
  { label: "Action", value: "Manager coaching + security review" },
];

// The raw narrative, broken into plain-text chunks and phrase chunks. Each
// phrase chunk's `field` is an index into REPORT_ANALYSIS — the card sweeps
// a highlight across the phrase that produced each fact, then resolves it
// below, so it *shows* the read instead of just listing conclusions.
const NARRATIVE_TOKENS: { text: string; field?: number }[] = [
  { text: "Customer got " },
  { text: "aggressive at the register", field: 2 },
  { text: " — " },
  { text: "third time this month", field: 0 },
  { text: ", so this falls under " },
  { text: "workplace violence prevention", field: 1 },
  { text: "." },
];

function DailyInstrument() {
  const reduce = useReducedMotion();
  const total = DAILY_BARS.reduce((a, b) => a + b, 0);
  const max = Math.max(...DAILY_BARS);
  const voicePhase = useCyclingIndex(VOICE_PHASE_COUNT, 1900, reduce);
  const listening = voicePhase === 1;
  const extractPhase = useCyclingIndex(REPORT_ANALYSIS.length, 2400, reduce);

  return (
    <InstrumentFrame label="Daily Intake" accent="#F2C14E">
      {/* Two-column layout so the card fills its width instead of stacking
          tall. Left = intake + the log; right = the AI analysis + voice. */}
      <div className="grid grid-cols-2 items-stretch">
      <div className="flex flex-col justify-between">
      <div className="px-5 pt-3 flex items-end justify-between">
        <div className="flex items-baseline gap-2">
          <span
            className="tabular-nums leading-none"
            style={{
              fontFamily: DISPLAY,
              fontWeight: 300,
              fontSize: "3.35rem",
              color: "#F2C14E",
            }}
          >
            {total}
          </span>
          <span className="text-[1rem]" style={{ color: ASH }}>
            /week
          </span>
          <span
            className="text-[10px] font-mono px-1.5 py-0.5 rounded"
            style={{
              color: "#86efac",
              backgroundColor: "rgba(134,239,172,0.1)",
            }}
          >
            ▲ 18%
          </span>
        </div>
        <div className="text-right">
          <div
            className="text-[11px] font-mono uppercase tracking-[0.2em]"
            style={{ color: "#F2C14E" }}
          >
            Reports
          </div>
          <div
            className="text-[10px] font-mono uppercase tracking-[0.16em]"
            style={{ color: ASH }}
          >
            via magic link
          </div>
        </div>
      </div>
      <div
        className="px-5 pt-4 pb-2 flex items-end gap-2.5"
        style={{ height: 60 }}
      >
        {DAILY_BARS.map((v, i) => {
          const h = (v / max) * 42;
          const pct = DAILY_BEHAVIORAL_PCT[i];
          return (
            <div key={i} className="flex-1 flex flex-col items-center gap-1.5">
              <motion.div
                className="w-full rounded-t-sm"
                style={{
                  background: `linear-gradient(to top, rgba(242,193,78,0.9) ${pct}%, rgba(242,193,78,0.38) ${pct}%)`,
                }}
                initial={{ height: 4 }}
                animate={
                  reduce ? { height: h } : { height: [4, h, h * 0.85, h] }
                }
                transition={
                  reduce
                    ? { duration: 0 }
                    : {
                        duration: 2.2,
                        repeat: Infinity,
                        repeatType: "mirror",
                        delay: i * 0.12,
                        ease: "easeInOut",
                      }
                }
              />
              <span className="text-[9px] font-mono" style={{ color: ASH }}>
                {DAILY_LABELS[i]}
              </span>
            </div>
          );
        })}
      </div>
      <div
        className="flex items-center gap-3 px-5 pb-3 pt-1 text-[9px] font-mono uppercase tracking-[0.12em]"
        style={{ color: ASH }}
      >
        <span className="inline-flex items-center gap-1.5">
          <span
            className="w-2 h-2 rounded-sm"
            style={{ backgroundColor: "rgba(242,193,78,0.9)" }}
          />
          Behavioral
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span
            className="w-2 h-2 rounded-sm"
            style={{ backgroundColor: "rgba(242,193,78,0.38)" }}
          />
          Safety
        </span>
      </div>
      {/* The log itself — actual logged records + their auto-categorization
          and severity, so the card shows the output, not just the intake. */}
      <div className="px-5 pt-3 pb-1 border-t" style={{ borderColor: LINE_D }}>
        <div className="flex items-center justify-between mb-2 mt-1">
          <span
            className="text-[9px] font-mono uppercase tracking-[0.16em]"
            style={{ color: ASH }}
          >
            Recent incidents
          </span>
          <span
            className="text-[9px] font-mono uppercase tracking-[0.16em]"
            style={{ color: ASH }}
          >
            Auto-categorized
          </span>
        </div>
        {RECENT_INCIDENTS.map((r, i) => (
          <motion.div
            key={r.loc}
            initial={reduce ? false : { opacity: 0, x: -6 }}
            whileInView={reduce ? undefined : { opacity: 1, x: 0 }}
            viewport={{ once: true, margin: "-20px" }}
            transition={{ delay: i * 0.1, duration: 0.4 }}
            className="flex items-center gap-2.5 py-1.5 border-t first:border-t-0"
            style={{ borderColor: "rgba(245,242,237,0.06)" }}
          >
            <span
              className="w-1.5 h-1.5 rounded-full shrink-0"
              style={{ backgroundColor: r.color }}
            />
            <span className="text-[11px] truncate" style={{ color: BONE }}>
              {r.loc}
            </span>
            <span
              className="text-[9px] font-mono truncate hidden sm:inline"
              style={{ color: ASH }}
            >
              {r.type}
            </span>
            <span
              className="ml-auto shrink-0 text-[8px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded"
              style={{ color: r.color, backgroundColor: `${r.color}1a` }}
            >
              {r.sev}
            </span>
          </motion.div>
        ))}
      </div>
      </div>
      {/* Right column — the AI does the work: analysis + voice intake. */}
      <div className="flex flex-col border-l" style={{ borderColor: LINE_D }}>
      {/* The report opened, with its analysis — pattern detection, policy
          mapping, recommended action. */}
      <div className="px-5 pt-3 pb-3" style={{ borderColor: LINE_D }}>
        <div className="flex items-center gap-2 mb-2.5">
          <span className="text-[10px] font-mono" style={{ color: BONE }}>
            IR-2041
          </span>
          <span
            className="text-[9px] font-mono truncate"
            style={{ color: ASH }}
          >
            Atlanta — Store 7
          </span>
          <span
            className="ml-auto shrink-0 text-[8px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded"
            style={{
              color: "#c98a3e",
              backgroundColor: "rgba(201,138,62,0.12)",
              border: "1px solid rgba(201,138,62,0.25)",
            }}
          >
            OSHA recordable
          </span>
        </div>
        <div className="flex items-center gap-1.5 mb-2.5">
          <Sparkles className="w-3 h-3 shrink-0" style={{ color: "#F2C14E" }} />
          <span
            className="text-[8px] font-mono uppercase tracking-[0.16em]"
            style={{ color: ASH }}
          >
            Agentic analysis
          </span>
          <span
            className="home-pulse w-1 h-1 rounded-full"
            style={{ backgroundColor: "#F2C14E" }}
          />
        </div>
        {/* The raw report, with the phrase behind the current fact lit up
            as it's "read" — shows the extraction happening instead of
            just listing what it found. */}
        <p
          className="text-[11px] leading-relaxed italic"
          style={{ color: ASH }}
        >
          “
          {NARRATIVE_TOKENS.map((t, i) => {
            const active = t.field === extractPhase;
            return (
              <span
                key={i}
                className="transition-colors duration-500 not-italic"
                style={
                  t.field === undefined
                    ? undefined
                    : {
                        color: active ? "#F2C14E" : ASH,
                        backgroundColor: active
                          ? "rgba(242,193,78,0.12)"
                          : "transparent",
                        borderRadius: 3,
                        padding: active ? "0 3px" : undefined,
                      }
                }
              >
                {t.text}
              </span>
            );
          })}
          ”
        </p>
        <div className="flex items-center gap-2 mt-2.5">
          <span className="text-[10px] shrink-0" style={{ color: "#F2C14E" }}>
            ↳
          </span>
          <AnimatePresence mode="wait">
            <motion.div
              key={extractPhase}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.3 }}
              className="flex items-baseline gap-2.5 min-w-0"
            >
              <span
                className="text-[8px] font-mono uppercase tracking-[0.12em] shrink-0"
                style={{ color: ASH }}
              >
                {REPORT_ANALYSIS[extractPhase].label}
              </span>
              <span
                className="text-[10px] leading-snug truncate"
                style={{ color: BONE }}
              >
                {REPORT_ANALYSIS[extractPhase].value}
              </span>
            </motion.div>
          </AnimatePresence>
        </div>
        <div
          className="flex items-center gap-3 mt-3 pt-2.5 border-t text-[8px] font-mono uppercase tracking-[0.12em]"
          style={{ borderColor: "rgba(245,242,237,0.06)", color: ASH }}
        >
          <span>2 witnesses</span>
          <span style={{ color: LINE_D }}>·</span>
          <span>3 photos</span>
          <span style={{ color: LINE_D }}>·</span>
          <span style={{ color: "#86efac" }}>Routed to manager</span>
        </div>
      </div>
      {/* Voice intake demo — same mockup as the dedicated section on
          /matcha-daily (magic link header, mic, waveform, extracted
          fields), just scaled to fit the hero card. Flush section like the
          one above it — same card, no inner box. */}
      <div
        className="px-5 pt-3 pb-4 border-t transition-colors duration-300"
        style={{ borderColor: listening ? "rgba(242,193,78,0.4)" : LINE_D }}
      >
        <div className="flex items-center gap-2 mb-3">
          <Lock className="w-2.5 h-2.5 shrink-0" style={{ color: ASH }} />
          <span
            className="text-[9px] font-mono truncate"
            style={{ color: ASH }}
          >
            hey-matcha.com/intake/atl7
          </span>
          <span
            className="ml-auto shrink-0 text-[7px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded"
            style={{ border: `1px solid ${LINE_D}`, color: ASH }}
          >
            Public form
          </span>
        </div>

        <div className="flex flex-col items-center text-center py-1">
          <span
            className="text-[8px] font-mono uppercase tracking-widest mb-3"
            style={{ color: ASH }}
          >
            Atlanta — Store 7
          </span>
          <div
            className="relative w-11 h-11 rounded-full flex items-center justify-center mb-2.5 transition-colors duration-300"
            style={{
              backgroundColor: listening
                ? "rgba(242,193,78,0.15)"
                : "rgba(245,242,237,0.05)",
              border: `1px solid ${listening ? "rgba(242,193,78,0.5)" : LINE_D}`,
            }}
          >
            {listening && (
              <span
                className="absolute inset-0 rounded-full animate-ping"
                style={{ backgroundColor: "rgba(242,193,78,0.2)" }}
              />
            )}
            <Mic
              className="w-5 h-5 relative"
              style={{ color: listening ? "#F2C14E" : ASH }}
            />
          </div>
          <div className="flex items-end gap-[2.5px] h-4 mb-2.5">
            {VOICE_WAVEFORM.map((v, i) => (
              <motion.div
                key={i}
                className="w-[2.5px] rounded-full"
                style={{
                  backgroundColor: listening ? "rgba(242,193,78,0.8)" : LINE_D,
                }}
                animate={
                  reduce
                    ? { height: listening ? `${v * 100}%` : "20%" }
                    : {
                        height: listening
                          ? [`${v * 55}%`, `${v * 100}%`, `${v * 55}%`]
                          : "20%",
                      }
                }
                transition={
                  reduce
                    ? { duration: 0 }
                    : {
                        duration: 0.8,
                        repeat: listening ? Infinity : 0,
                        delay: i * 0.05,
                        ease: "easeInOut",
                      }
                }
              />
            ))}
          </div>
          <AnimatePresence mode="wait">
            <motion.span
              key={voicePhase}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.3 }}
              className="text-[10px] font-mono"
              style={{
                color:
                  voicePhase === 1
                    ? "#F2C14E"
                    : voicePhase === 3
                      ? "#86efac"
                      : ASH,
              }}
            >
              {voicePhase < 3
                ? VOICE_STATUS[voicePhase]
                : "Report ready for review"}
            </motion.span>
          </AnimatePresence>
        </div>

        <div
          className="grid grid-cols-2 gap-2.5 mt-3 pt-3 border-t transition-opacity duration-500"
          style={{
            borderColor: "rgba(245,242,237,0.06)",
            opacity: voicePhase === 3 ? 1 : 0.25,
          }}
        >
          <div>
            <div
              className="text-[7px] font-mono uppercase tracking-widest mb-0.5"
              style={{ color: ASH }}
            >
              Category
            </div>
            <div className="text-[10px]" style={{ color: BONE }}>
              Customer escalation
            </div>
          </div>
          <div>
            <div
              className="text-[7px] font-mono uppercase tracking-widest mb-0.5"
              style={{ color: ASH }}
            >
              Severity
            </div>
            <div
              className="text-[10px] font-medium"
              style={{ color: "#F2C14E" }}
            >
              Medium
            </div>
          </div>
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
          Reviewed before it submits
        </span>
        <span
          className="text-[9px] font-mono uppercase tracking-[0.16em] shrink-0 ml-2"
          style={{ color: ASH }}
        >
          Talk or type
        </span>
      </div>
    </InstrumentFrame>
  );
}

// OSHA-recordable rows for the 300-log mock. Real column set + classification
// labels from the shipped OshaLogsPanel; one row shows a privacy-masked case
// (29 CFR 1904.29 — the log prints "Privacy Case", not the name).
const OSHA_300A_TILES = [
  { label: "Total Cases", value: "4", color: BONE },
  { label: "Deaths", value: "0", color: "#ce5a4f" },
  { label: "Days Away", value: "2", sub: "cases", color: "#F2C14E" },
  { label: "Restricted", value: "1", sub: "cases", color: "#c98a3e" },
];
const OSHA_ROWS = [
  {
    caseNo: "IR-2041-1",
    name: "A. Rivera",
    cls: "Days Away",
    clsColor: "#F2C14E",
    days: "3",
    privacy: false,
  },
  {
    caseNo: "IR-2033-1",
    name: "J. Okafor",
    cls: "Restricted Duty",
    clsColor: "#c98a3e",
    days: "5",
    privacy: false,
  },
  {
    caseNo: "IR-2027-1",
    name: "Privacy Case",
    cls: "Medical Treatment",
    clsColor: ASH,
    days: "—",
    privacy: true,
  },
];
const OSHA_EXPORTS = ["300 CSV", "300A CSV", "300A PDF", "ITA Export"];

function OshaLogInstrument() {
  const reduce = useReducedMotion();
  return (
    <InstrumentFrame label="OSHA 300 Log" accent="#F2C14E">
      {/* Two-column: left = headline + 300A roll-up + exports, right = the
          Form 300 log itself. */}
      <div className="grid grid-cols-2 items-stretch">
      <div className="flex flex-col justify-between">
      {/* Recordables headline — the payoff of flipping "OSHA recordable" on an
          incident: it lands here, per establishment, per year. */}
      <div className="px-5 pt-4 flex items-end justify-between">
        <div className="flex items-baseline gap-2">
          <span
            className="tabular-nums leading-none"
            style={{
              fontFamily: DISPLAY,
              fontWeight: 300,
              fontSize: "3rem",
              color: "#F2C14E",
            }}
          >
            4
          </span>
          <span className="text-[0.85rem]" style={{ color: ASH }}>
            recordable YTD
          </span>
        </div>
        <div className="text-right">
          <div
            className="text-[11px] font-mono uppercase tracking-[0.18em]"
            style={{ color: BONE }}
          >
            Atlanta — Store 7
          </div>
          <div
            className="text-[10px] font-mono uppercase tracking-[0.16em]"
            style={{ color: ASH }}
          >
            Establishment · 2026
          </div>
        </div>
      </div>

      {/* 300A summary tiles — the annual roll-up, auto-computed from the log. */}
      <div className="px-5 pt-4 grid grid-cols-2 gap-2">
        {OSHA_300A_TILES.map((t) => (
          <div
            key={t.label}
            className="rounded-lg border px-2.5 py-2"
            style={{
              borderColor: LINE_D,
              backgroundColor: "rgba(245,242,237,0.02)",
            }}
          >
            <div
              className="tabular-nums leading-none mb-1"
              style={{
                fontFamily: DISPLAY,
                fontWeight: 400,
                fontSize: "1.4rem",
                color: t.color,
              }}
            >
              {t.value}
            </div>
            <div
              className="text-[7px] font-mono uppercase tracking-[0.1em]"
              style={{ color: ASH }}
            >
              {t.label}
              {t.sub ? ` · ${t.sub}` : ""}
            </div>
          </div>
        ))}
      </div>

      {/* One-tap exports — the shipped file set (300 CSV / 300A CSV / 300A PDF
          / ITA), each behind a reviewer attestation. */}
      <div className="px-5 pt-4 pb-4 flex flex-wrap gap-1.5">
        {OSHA_EXPORTS.map((e) => (
          <span
            key={e}
            className="inline-flex items-center gap-1.5 text-[8px] font-mono uppercase tracking-wider px-2 py-1 rounded"
            style={{ border: `1px solid ${LINE_D}`, color: ASH }}
          >
            <FileText className="w-2.5 h-2.5" style={{ color: "#F2C14E" }} />
            {e}
          </span>
        ))}
      </div>
      </div>
      {/* Right column — the Form 300 log itself. */}
      <div className="flex flex-col border-l" style={{ borderColor: LINE_D }}>
      {/* Form 300 rows — real columns: Case # / Employee / Classification /
          Days. The privacy row prints the mask, never the name. */}
      <div className="px-5 pt-4 pb-4">
        <div className="flex items-center justify-between mb-2">
          <span
            className="text-[8px] font-mono uppercase tracking-[0.16em]"
            style={{ color: ASH }}
          >
            Form 300 · Log of injuries &amp; illnesses
          </span>
          <span
            className="text-[8px] font-mono uppercase tracking-[0.16em]"
            style={{ color: "#86efac" }}
          >
            ● Recordable
          </span>
        </div>
        <div
          className="grid items-center gap-2 pb-1.5 mb-1 border-b text-[7px] font-mono uppercase tracking-[0.1em]"
          style={{
            gridTemplateColumns: "auto 1fr auto auto",
            borderColor: LINE_D,
            color: ASH,
          }}
        >
          <span>Case #</span>
          <span>Employee</span>
          <span>Classification</span>
          <span className="text-right">Days</span>
        </div>
        {OSHA_ROWS.map((r, i) => (
          <motion.div
            key={r.caseNo}
            initial={reduce ? false : { opacity: 0, x: -6 }}
            whileInView={reduce ? undefined : { opacity: 1, x: 0 }}
            viewport={{ once: true, margin: "-20px" }}
            transition={{ delay: i * 0.1, duration: 0.4 }}
            className="grid items-center gap-2 py-1.5 border-t first:border-t-0"
            style={{
              gridTemplateColumns: "auto 1fr auto auto",
              borderColor: "rgba(245,242,237,0.06)",
            }}
          >
            <span
              className="text-[9px] font-mono tabular-nums"
              style={{ color: ASH }}
            >
              {r.caseNo}
            </span>
            <span className="flex items-center gap-1.5 min-w-0">
              {r.privacy && (
                <Lock className="w-2.5 h-2.5 shrink-0" style={{ color: ASH }} />
              )}
              <span
                className="text-[10px] truncate"
                style={{
                  color: r.privacy ? ASH : BONE,
                  fontStyle: r.privacy ? "italic" : "normal",
                }}
              >
                {r.name}
              </span>
            </span>
            <span
              className="shrink-0 text-[8px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded"
              style={{ color: r.clsColor, backgroundColor: `${r.clsColor}1a` }}
            >
              {r.cls}
            </span>
            <span
              className="text-[10px] tabular-nums text-right"
              style={{ color: BONE }}
            >
              {r.days}
            </span>
          </motion.div>
        ))}
      </div>

      </div>
      </div>

      <div
        className="flex items-center justify-between px-5 pb-4 pt-3 border-t"
        style={{ borderColor: LINE_D }}
      >
        <span
          className="text-[9px] font-mono uppercase tracking-[0.16em]"
          style={{ color: "#86efac" }}
        >
          300A ready for Feb 1 posting
        </span>
        <span
          className="text-[9px] font-mono uppercase tracking-[0.16em] shrink-0 ml-2"
          style={{ color: ASH }}
        >
          Per establishment
        </span>
      </div>
    </InstrumentFrame>
  );
}

const COMPLIANCE_CHIPS = [
  { code: "CA", resolved: true },
  { code: "NY", resolved: true },
  { code: "FED", resolved: false },
  { code: "WA", resolved: false },
  { code: "IL", resolved: false },
  { code: "TX", resolved: false },
];

type FindingStatus = "flagged" | "fixing" | "fixed";

const COMPLIANCE_FINDINGS: { state: string; text: string }[] = [
  { state: "CA", text: "Meal period waivers missing for 12 employees" },
  { state: "NY", text: "Paid sick leave accrual rate below statute" },
  { state: "FED", text: "FLSA overtime threshold update not applied" },
  { state: "WA", text: "Predictive scheduling notice window expired" },
  { state: "IL", text: "BIPA biometric consent forms unsigned" },
  { state: "TX", text: "Anti-retaliation posters out of date" },
];

// AI action layer — grounded in the real product's legislation-watch worker
// + alerts/action-plans (root CLAUDE.md). Cycles like Platform's ER Copilot.
const COMPLIANCE_COPILOT = [
  "Legislation watch: new CA pay-transparency rule effective Jul 1.",
  "Action plan: file WA predictive-scheduling notice by Mar 14.",
  "Auto-drafted: updated anti-retaliation poster ready to post.",
];

// Coverage across compliance areas, not just jurisdictions — the breadth grid,
// mirroring Platform's domain grid. Illustrative.
const COMPLIANCE_CATEGORIES = [
  { label: "Wage & Hour", status: "Gap", color: "#E2725B" },
  { label: "Leave & Sick", status: "Clear", color: "#86efac" },
  { label: "Safety / OSHA", status: "Gap", color: "#E2725B" },
  { label: "Posting", status: "Scan", color: "#d9b65f" },
  { label: "Classification", status: "Clear", color: "#86efac" },
  { label: "Pay Equity", status: "Clear", color: "#86efac" },
] as const;

const FINDING_ICON = {
  flagged: AlertTriangle,
  fixing: Loader2,
  fixed: CheckCircle2,
} as const;
const FINDING_COLOR = {
  flagged: "#E2725B",
  fixing: "#d9b65f",
  fixed: "#86efac",
} as const;

// Mirrors the real flag → fixing → fixed cascade from the actual /compliance
// page's live engine, staggered per row and looping, instead of a static list.
function useFindingsCascade(count: number, reduce: boolean) {
  const [statuses, setStatuses] = useState<FindingStatus[]>(() =>
    Array(count).fill("flagged"),
  );

  useEffect(() => {
    if (reduce) {
      setStatuses(
        Array.from({ length: count }, (_, i) => (i < 2 ? "fixed" : "flagged")),
      );
      return;
    }
    const STEP = 1600;
    const ROW_STAGGER = 900;
    const CYCLE = STEP * 2 + count * ROW_STAGGER + 2000;
    let timers: number[] = [];

    const runCycle = () => {
      setStatuses(Array(count).fill("flagged"));
      for (let i = 0; i < count; i++) {
        timers.push(
          window.setTimeout(
            () => {
              setStatuses((s) => s.map((v, j) => (j === i ? "fixing" : v)));
            },
            STEP + i * ROW_STAGGER,
          ),
        );
        timers.push(
          window.setTimeout(
            () => {
              setStatuses((s) => s.map((v, j) => (j === i ? "fixed" : v)));
            },
            STEP * 2 + i * ROW_STAGGER,
          ),
        );
      }
    };

    runCycle();
    const loop = window.setInterval(runCycle, CYCLE);
    return () => {
      timers.forEach((t) => window.clearTimeout(t));
      window.clearInterval(loop);
      timers = [];
    };
  }, [count, reduce]);

  return statuses;
}

function ComplianceInstrument() {
  const TARGET = 60;
  const reduce = useReducedMotion();
  const [score, setScore] = useState(reduce ? TARGET : 0);
  const copilotIndex = useCyclingIndex(COMPLIANCE_COPILOT.length, 3200, reduce);
  const findingStatuses = useFindingsCascade(
    COMPLIANCE_FINDINGS.length,
    reduce,
  );

  useEffect(() => {
    if (reduce) return;
    const DUR = 1200;
    let raf = 0;
    let start = 0;
    const loop = (now: number) => {
      if (!start) start = now;
      const e = now - start;
      const intro = Math.min(1, e / DUR);
      const eased = 1 - Math.pow(1 - intro, 3);
      setScore(Math.round(eased * TARGET));
      if (intro < 1) raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [reduce]);

  const resolvedCount = COMPLIANCE_CHIPS.filter((c) => c.resolved).length;

  return (
    <InstrumentFrame label="Compliance Monitor" accent="#E2725B">
      {/* Two-column: left = score + jurisdictions + the AI copilot, right =
          the live findings cascade. Coverage grid spans full width below. */}
      <div className="grid grid-cols-2 items-stretch">
      <div className="flex flex-col justify-between">
      <div className="px-5 pt-4 flex items-end justify-between">
        <span
          className="tabular-nums leading-none"
          style={{
            fontFamily: DISPLAY,
            fontWeight: 300,
            fontSize: "3.5rem",
            color: "#E2725B",
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
            style={{ color: "#E2725B" }}
          >
            {resolvedCount}/{COMPLIANCE_CHIPS.length} resolved
          </div>
          <div
            className="text-[10px] font-mono uppercase tracking-[0.16em]"
            style={{ color: ASH }}
          >
            Next: WA in 9d
          </div>
        </div>
      </div>
      <div className="px-5 pt-5 flex flex-wrap gap-2">
        {COMPLIANCE_CHIPS.map((c) => (
          <span
            key={c.code}
            className="px-2.5 py-1 rounded-full text-[10px] font-mono uppercase tracking-wider"
            style={{
              border: `1px solid ${c.resolved ? "rgba(134,239,172,0.35)" : "rgba(226,114,91,0.35)"}`,
              color: c.resolved ? "#86efac" : "#E2725B",
              backgroundColor: c.resolved
                ? "rgba(134,239,172,0.08)"
                : "rgba(226,114,91,0.08)",
            }}
          >
            {c.code} {c.resolved ? "✓" : "!"}
          </span>
        ))}
      </div>
      <div className="px-5 pt-4 pb-4">
        <div
          className="rounded-lg px-3.5 py-2.5 flex items-start gap-2.5"
          style={{
            border: `1px solid ${LINE_D}`,
            backgroundColor: "rgba(245,242,237,0.03)",
          }}
        >
          <Sparkles
            className="w-3.5 h-3.5 mt-0.5 shrink-0"
            style={{ color: "#E2725B" }}
          />
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 mb-1">
              <span
                className="text-[8px] font-mono uppercase tracking-[0.16em]"
                style={{ color: ASH }}
              >
                Compliance Copilot
              </span>
              <span
                className="home-pulse w-1 h-1 rounded-full"
                style={{ backgroundColor: "#E2725B" }}
              />
            </div>
            <AnimatePresence mode="wait">
              <motion.p
                key={copilotIndex}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.4 }}
                className="text-[11px] leading-snug"
                style={{ color: BONE }}
              >
                {COMPLIANCE_COPILOT[copilotIndex]}
              </motion.p>
            </AnimatePresence>
          </div>
        </div>
      </div>
      </div>
      {/* Right column — the flag → fixing → fixed cascade. */}
      <div className="flex flex-col border-l" style={{ borderColor: LINE_D }}>
      <div className="px-5 pb-3 pt-3">
        {COMPLIANCE_FINDINGS.map((f, i) => {
          const status = findingStatuses[i];
          const Icon = FINDING_ICON[status];
          return (
            <div key={f.state} className="flex items-center gap-2.5 py-1.5">
              <span
                className="text-[9px] font-mono px-1.5 py-0.5 rounded shrink-0"
                style={{ border: `1px solid ${LINE_D}`, color: ASH }}
              >
                {f.state}
              </span>
              <span
                className="text-[11px] flex-1 truncate transition-colors duration-300"
                style={{
                  color: status === "fixed" ? ASH : BONE,
                  textDecoration:
                    status === "fixed"
                      ? "line-through rgba(245,242,237,0.4)"
                      : "none",
                }}
              >
                {f.text}
              </span>
              <Icon
                className={`w-3.5 h-3.5 shrink-0 ${status === "fixing" ? "animate-spin" : ""}`}
                style={{ color: FINDING_COLOR[status] }}
              />
            </div>
          );
        })}
      </div>
      </div>
      </div>
      {/* Breadth — coverage across every compliance area, not just the open
          findings. Mirrors Platform's domain grid. Spans full width below
          the two columns. */}
      <div
        className="px-5 pt-4 pb-4 border-t"
        style={{ borderColor: LINE_D }}
      >
        <div className="flex items-center justify-between mb-2.5">
          <span
            className="text-[8px] font-mono uppercase tracking-[0.16em]"
            style={{ color: ASH }}
          >
            Coverage by area
          </span>
          <span
            className="text-[8px] font-mono uppercase tracking-[0.16em]"
            style={{ color: ASH }}
          >
            247 reqs
          </span>
        </div>
        <div
          className="grid grid-cols-3 rounded-lg overflow-hidden border"
          style={{
            borderColor: LINE_D,
            backgroundColor: "rgba(245,242,237,0.02)",
          }}
        >
          {COMPLIANCE_CATEGORIES.map((c, i) => (
            <div
              key={c.label}
              className="px-2.5 py-2"
              style={gridCellBorderStyle(i, COMPLIANCE_CATEGORIES.length)}
            >
              <div className="flex items-center gap-1.5 mb-1">
                <span
                  className="w-1.5 h-1.5 rounded-full shrink-0"
                  style={{ backgroundColor: c.color }}
                />
                <span
                  className="text-[8px] font-mono uppercase tracking-[0.1em] truncate"
                  style={{ color: ASH }}
                >
                  {c.label}
                </span>
              </div>
              <span
                className="text-[11px] font-mono"
                style={{ color: c.color }}
              >
                {c.status}
              </span>
            </div>
          ))}
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
          247 requirements scanned
        </span>
        <span
          className="text-[9px] font-mono uppercase tracking-[0.16em]"
          style={{ color: ASH }}
        >
          Updated just now
        </span>
      </div>
    </InstrumentFrame>
  );
}

const INSTRUMENT_COMPONENTS = [
  DailyInstrument,
  OshaLogInstrument,
  ComplianceInstrument,
  PlatformInstrument,
];
const SHOWCASE_INTERVAL = 6000;

function ProductCarousel() {
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

// ---------------------------------------------------------------------------
// Product index — big editorial rows that color-wash on hover
// ---------------------------------------------------------------------------

function ProductIndex() {
  const [hovered, setHovered] = useState<number | null>(null);

  return (
    <section id="index" className="scroll-mt-16 py-20 sm:py-28">
      <div className="max-w-[1600px] mx-auto w-full px-6 sm:px-10">
        <div className="flex items-baseline justify-between mb-2">
          <h2
            className="text-[11px] tracking-[0.3em] font-mono uppercase"
            style={{ color: ASH }}
          >
            Four ways in
          </h2>
          <span
            className="text-[11px] tracking-[0.3em] font-mono uppercase"
            style={{ color: ASH }}
          >
            Index
          </span>
        </div>

        <div className="border-t" style={{ borderColor: LINE_D }}>
          {PRODUCTS.map((p, i) => {
            const active = hovered === i;
            return (
              <Link
                key={p.name}
                to={p.to}
                onMouseEnter={() => setHovered(i)}
                onMouseLeave={() => setHovered(null)}
                className="group relative grid grid-cols-[auto_1fr] sm:grid-cols-[auto_1fr_auto] items-center gap-x-5 sm:gap-x-10 border-b px-2 sm:px-6 py-7 sm:py-10 transition-colors duration-300"
                style={{
                  borderColor: LINE_D,
                  backgroundColor: active ? p.accent : "transparent",
                  color: active ? NOIR : BONE,
                }}
              >
                <span
                  className="font-mono text-sm sm:text-base self-start pt-2 sm:pt-4 transition-colors duration-300"
                  style={{ color: active ? NOIR : p.accent }}
                >
                  {p.n}
                </span>

                <div className="min-w-0">
                  <h3
                    className="tracking-[-0.02em] transition-transform duration-300 group-hover:translate-x-2"
                    style={{
                      fontFamily: DISPLAY,
                      fontWeight: 400,
                      lineHeight: 0.95,
                      fontSize: "clamp(2.25rem, 7vw, 5.5rem)",
                    }}
                  >
                    {p.name}
                  </h3>
                  <p
                    className="mt-3 max-w-2xl text-[15px] sm:text-lg transition-colors duration-300"
                    style={{
                      color: active ? "rgba(14,14,12,0.72)" : ASH,
                      lineHeight: 1.5,
                    }}
                  >
                    {p.blurb}
                  </p>
                </div>

                <span
                  className="hidden sm:inline-flex items-center gap-2 font-mono text-sm uppercase tracking-[0.2em] justify-self-end transition-all duration-300"
                  style={{
                    color: active ? NOIR : BONE,
                    opacity: active ? 1 : 0.55,
                  }}
                >
                  Enter
                  <span
                    className="transition-transform duration-300 group-hover:translate-x-1.5"
                    aria-hidden
                  >
                    →
                  </span>
                </span>
              </Link>
            );
          })}
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Manifesto — full-bleed matcha color block, hard editorial cut
// ---------------------------------------------------------------------------

function Manifesto() {
  return (
    <section
      style={{ backgroundColor: MATCHA, color: NOIR }}
      className="py-24 sm:py-36"
    >
      <div className="max-w-[1400px] mx-auto px-6 sm:px-10">
        <span className="text-[11px] tracking-[0.3em] font-mono uppercase">
          The point
        </span>
        <p
          className="mt-8 tracking-[-0.02em]"
          style={{
            fontFamily: DISPLAY,
            fontWeight: 300,
            lineHeight: 1.04,
            fontSize: "clamp(2rem, 5.5vw, 4.75rem)",
          }}
        >
          We don&rsquo;t ship software and walk away. We take responsibility for
          the hardest, most <span style={{ fontStyle: "italic" }}>human</span>{" "}
          part of your company.
        </p>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Closing CTA
// ---------------------------------------------------------------------------

function CTABand({ onDemoClick }: { onDemoClick: () => void }) {
  return (
    <section className="py-28 sm:py-40">
      <div className="max-w-[1400px] mx-auto px-6 sm:px-10 text-center">
        <h2
          className="tracking-[-0.02em]"
          style={{
            fontFamily: DISPLAY,
            fontWeight: 300,
            lineHeight: 0.92,
            fontSize: "clamp(2.75rem, 9vw, 8rem)",
          }}
        >
          Find your{" "}
          <span style={{ color: MATCHA, fontStyle: "italic" }}>
            starting line.
          </span>
        </h2>
        <p
          className="mt-7 mx-auto max-w-lg text-lg"
          style={{ color: ASH, lineHeight: 1.5 }}
        >
          Tell us where you are. We&rsquo;ll tell you which of the four is the
          right place to begin.
        </p>
        <div className="mt-10 flex flex-wrap items-center justify-center gap-5">
          <button
            onClick={onDemoClick}
            className="inline-flex items-center px-8 rounded-full text-base font-medium transition-transform hover:-translate-y-0.5 cursor-pointer"
            style={{ backgroundColor: MATCHA, color: NOIR, height: 56 }}
          >
            Request a Demo
          </button>
          <a
            href="#index"
            className="inline-flex items-center gap-2 text-base transition-opacity hover:opacity-60"
            style={{ color: BONE }}
          >
            Browse the four
            <span aria-hidden>↑</span>
          </a>
        </div>
      </div>
    </section>
  );
}
