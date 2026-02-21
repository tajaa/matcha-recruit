import React, { useEffect, useRef, useState, useLayoutEffect } from "react";
import { Link } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import gsap from "gsap";
import ScrollTrigger from "gsap/ScrollTrigger";
import {
  MapPin,
  X,
  Send,
  Sparkles,
  Zap,
  Cpu,
  FileText,
  Shield,
  Activity,
} from "lucide-react";

gsap.registerPlugin(ScrollTrigger);

// --- SYNTHESIZED DESIGN TOKENS ---
// Deep Obsidian/Forest background with Cream and Neon Moss/Clay accents.
const theme = {
  obsidian: "#0A0E0C",
  cream: "#F0EFEA",
  moss: "#4ADE80", // Glowing organic tech
  clay: "#D95A38", // Biological warmth
  glass: "rgba(240, 239, 234, 0.03)",
  border: "rgba(240, 239, 234, 0.08)",
};

const fonts = {
  sans: '"Plus Jakarta Sans", "Inter", sans-serif',
  serif: '"Cormorant Garamond", serif',
  mono: '"JetBrains Mono", monospace',
};

// --- DATA ---
const LOCAL_JURISDICTIONS = [
  "San Francisco Local",
  "West Hollywood Local",
  "Los Angeles Local",
  "Seattle Local",
];

// --- MICRO-COMPONENTS ---

// 1. Organic Noise overlay (Ex Machina style film grain)
const CinematicNoise = () => (
  <div
    className="pointer-events-none fixed inset-0 z-[100] opacity-[0.06] mix-blend-screen"
    style={{
      backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E")`,
    }}
  />
);

// 2. Horizontal-Line ASCII Component (Matches your uploaded screenshot style)
// Uses tight line-height and horizontal box-drawing characters to create organic shapes
const HorizontalAsciiEntity = () => {
  const [phase, setPhase] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => setPhase((p) => (p + 1) % 100), 50);
    return () => clearInterval(interval);
  }, []);

  // Generates a flowing, organic shape using horizontal lines of varying weights
  const generateLines = () => {
    const lines = [];
    for (let i = 0; i < 24; i++) {
      const offset = Math.sin((i + phase * 0.5) * 0.2) * 10;
      const width = Math.max(10, 30 + Math.sin((i - phase * 0.3) * 0.4) * 20);

      // Select character based on "density"
      const char = width > 40 ? "━" : width > 25 ? "─" : "-";

      const padding = " ".repeat(Math.max(0, Math.floor(20 + offset)));
      const lineStr = char.repeat(Math.floor(width));
      lines.push(padding + lineStr);
    }
    return lines.join("\n");
  };

  return (
    <div className="relative group">
      {/* Ambient glow */}
      <div className="absolute inset-0 bg-[#4ADE80] opacity-10 blur-[50px] rounded-full mix-blend-screen group-hover:opacity-20 transition-opacity duration-1000" />
      <pre
        className="relative z-10 font-mono text-[10px] leading-[0.6] tracking-tighter text-[#4ADE80] transition-colors duration-700 select-none whitespace-pre"
        style={{ textShadow: "0 0 10px rgba(74, 222, 128, 0.4)" }}
      >
        {generateLines()}
      </pre>
      <div className="absolute top-0 right-0 text-[#F0EFEA]/30 text-[8px] font-mono uppercase tracking-[0.3em]">
        Neural Entity / Active
      </div>
    </div>
  );
};

// 3. Dynamic Telemetry Badge
const TelemetryBadge = ({
  text,
  active = false,
}: {
  text: string;
  active?: boolean;
}) => (
  <span
    className={`inline-flex items-center gap-2 px-3 py-1 rounded-full border text-[9px] font-mono uppercase tracking-widest backdrop-blur-md transition-colors duration-500
    ${active ? "border-[#4ADE80]/30 bg-[#4ADE80]/10 text-[#4ADE80]" : "border-[#F0EFEA]/10 bg-[#F0EFEA]/5 text-[#F0EFEA]/60"}`}
  >
    {active && (
      <span
        className="w-1.5 h-1.5 bg-[#4ADE80] rounded-full animate-pulse"
        style={{ boxShadow: "0 0 8px #4ADE80" }}
      />
    )}
    {text}
  </span>
);

// --- MAIN LANDING PAGE ---

export function Landing() {
  const containerRef = useRef<HTMLDivElement>(null);
  const manifestoRef = useRef<HTMLDivElement>(null);
  const systemRef = useRef<HTMLDivElement>(null);

  const [jurisdictionIndex, setJurisdictionIndex] = useState(0);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const timer = setInterval(() => {
      setJurisdictionIndex((prev) => (prev + 1) % LOCAL_JURISDICTIONS.length);
    }, 4000);

    const handleScroll = () => setScrolled(window.scrollY > 50);
    window.addEventListener("scroll", handleScroll);
    return () => {
      clearInterval(timer);
      window.removeEventListener("scroll", handleScroll);
    };
  }, []);

  useLayoutEffect(() => {
    const ctx = gsap.context(() => {
      // Cinematic text reveal
      gsap.from(".reveal-text", {
        y: 80,
        opacity: 0,
        stagger: 0.15,
        duration: 1.5,
        ease: "power4.out",
        delay: 0.2,
      });

      // Subtle parallax on backgrounds
      gsap.utils.toArray(".parallax-bg").forEach((bg: any) => {
        gsap.to(bg, {
          yPercent: 20,
          ease: "none",
          scrollTrigger: {
            trigger: bg.parentElement,
            start: "top bottom",
            end: "bottom top",
            scrub: true,
          },
        });
      });

      // Sticky Archive Animation (System Modules)
      const cards = gsap.utils.toArray(".system-card");
      cards.forEach((card: any, i: number) => {
        if (i === cards.length - 1) return;
        gsap.to(card, {
          scale: 0.92,
          filter: "blur(8px)",
          opacity: 0.4,
          scrollTrigger: {
            trigger: cards[i + 1] as HTMLElement,
            start: "top bottom",
            end: "top top",
            scrub: true,
          },
        });
      });
    }, containerRef);
    return () => ctx.revert();
  }, []);

  const scrollTo = (ref: React.RefObject<HTMLDivElement | null>) => {
    ref.current?.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <div
      ref={containerRef}
      className="bg-[#0A0E0C] text-[#F0EFEA] selection:bg-[#4ADE80] selection:text-[#0A0E0C] overflow-x-hidden min-h-screen"
    >
      <CinematicNoise />

      {/* NAVBAR (Glass Island) */}
      <nav className="fixed top-6 left-1/2 -translate-x-1/2 z-50 w-[92%] max-w-[1600px]">
        <div
          className={`flex items-center justify-between px-6 py-4 rounded-[2rem] transition-all duration-700 border ${
            scrolled
              ? "bg-[#0A0E0C]/60 backdrop-blur-xl border-[#F0EFEA]/10 shadow-2xl"
              : "bg-transparent border-transparent"
          }`}
        >
          <Link to="/" className="flex items-center gap-3 group">
            <div className="w-8 h-8 rounded-full border border-[#F0EFEA]/20 flex items-center justify-center overflow-hidden">
              <div className="w-full h-full bg-[#4ADE80] opacity-0 group-hover:opacity-20 transition-opacity duration-500" />
            </div>
            <span className="font-sans text-sm font-bold tracking-[0.2em] uppercase">
              Matcha
            </span>
          </Link>
          <div className="hidden md:flex gap-10 text-[10px] font-mono uppercase tracking-[0.2em] text-[#F0EFEA]/60">
            <span
              onClick={() => scrollTo(manifestoRef)}
              className="hover:text-[#4ADE80] cursor-pointer transition-colors"
            >
              Philosophy
            </span>
            <span
              onClick={() => scrollTo(systemRef)}
              className="hover:text-[#4ADE80] cursor-pointer transition-colors"
            >
              Architecture
            </span>
            <span className="hover:text-[#4ADE80] cursor-pointer transition-colors">
              Pricing
            </span>
          </div>
          <Link
            to="/login"
            className="px-6 py-2.5 rounded-full border border-[#F0EFEA]/20 text-[10px] font-mono uppercase tracking-[0.2em] hover:bg-[#F0EFEA] hover:text-[#0A0E0C] transition-all duration-500"
          >
            Access System
          </Link>
        </div>
      </nav>

      {/* HERO SECTION (Synthesized Elegance & Tech) */}
      <section className="relative h-screen flex flex-col justify-center px-6 md:px-16 overflow-hidden">
        {/* Abstract Organic/Tech Background */}
        <div className="absolute inset-0 z-0 overflow-hidden">
          <div
            className="parallax-bg absolute -inset-[10%] bg-cover bg-center opacity-40 mix-blend-screen grayscale"
            style={{
              backgroundImage: `url('https://images.unsplash.com/photo-1550684848-fac1c5b4e853?q=80&w=3500&auto=format&fit=crop')`,
            }}
          />
          <div className="absolute inset-0 bg-gradient-to-t from-[#0A0E0C] via-[#0A0E0C]/80 to-transparent" />
          <div className="absolute inset-0 bg-gradient-to-r from-[#0A0E0C] via-transparent to-transparent" />
        </div>

        <div className="relative z-20 w-full max-w-[1600px] mx-auto grid lg:grid-cols-12 gap-12 items-center">
          <div className="lg:col-span-8 flex flex-col items-start">
            <TelemetryBadge text="Core System v2.4 Online" active />

            <h1 className="mt-8 leading-[0.85] tracking-tighter mix-blend-lighten">
              <span
                className="reveal-text block text-[4rem] md:text-[7rem] font-bold uppercase"
                style={{ fontFamily: fonts.sans }}
              >
                Workforce
              </span>
              <span
                className="reveal-text block text-[5rem] md:text-[8rem] italic font-light text-[#D95A38]"
                style={{ fontFamily: fonts.serif }}
              >
                Intelligence.
              </span>
            </h1>

            <p
              className="reveal-text mt-8 text-[#F0EFEA]/60 text-lg md:text-xl font-light leading-relaxed max-w-xl"
              style={{ fontFamily: fonts.sans }}
            >
              The operating system for modern workforce management. <br />
              Stripped of administrative noise. Engineered for biological
              clarity.
            </p>
          </div>

          <div className="hidden lg:flex lg:col-span-4 justify-end items-center">
            {/* Floating ASCII Element in Hero */}
            <div className="w-[300px] h-[300px] rounded-full border border-[#4ADE80]/20 flex items-center justify-center relative backdrop-blur-sm">
              <div className="absolute inset-0 border border-[#4ADE80]/10 rounded-full scale-[1.2] animate-[spin_20s_linear_infinite]" />
              <HorizontalAsciiEntity />
            </div>
          </div>
        </div>
      </section>

      {/* COMPLIANCE / PRECISION MICRO-UI (Glass on Obsidian) */}
      <section className="py-40 px-6 relative">
        <div className="max-w-[1600px] mx-auto grid lg:grid-cols-2 gap-24 items-center">
          <div className="space-y-12 pr-12">
            <h2
              className="text-4xl md:text-6xl font-bold tracking-tighter leading-[0.9]"
              style={{ fontFamily: fonts.sans }}
            >
              HIERARCHICAL <br />
              <span
                className="italic text-[#4ADE80] font-light"
                style={{ fontFamily: fonts.serif }}
              >
                Jurisdiction Mapping.
              </span>
            </h2>
            <p className="text-[#F0EFEA]/60 text-xl font-light leading-relaxed">
              Matcha autonomously monitors labor laws across city, county, and
              state levels—deploying the precise algorithmic rule for every
              employee endpoint.
            </p>
            <div className="flex gap-4">
              <button className="px-6 py-3 bg-[#4ADE80] text-[#0A0E0C] rounded-full text-[10px] font-mono uppercase tracking-widest hover:bg-white transition-colors">
                View Coverage
              </button>
            </div>
          </div>

          <div className="relative">
            {/* Glassmorphic Clinical Cards */}
            <div className="relative z-10 space-y-6">
              <motion.div
                animate={{ y: [0, -15, 0] }}
                transition={{
                  duration: 8,
                  repeat: Infinity,
                  ease: "easeInOut",
                }}
                className="bg-white/[0.02] backdrop-blur-2xl rounded-[2rem] border border-white/10 p-8 shadow-[0_0_50px_rgba(0,0,0,0.5)] overflow-hidden"
              >
                {/* Tech Scanner Line */}
                <motion.div
                  animate={{ top: ["-10%", "110%"] }}
                  transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
                  className="absolute left-0 right-0 h-[1px] bg-[#4ADE80]/50 shadow-[0_0_20px_#4ADE80] z-30"
                />

                <div className="flex justify-between items-center mb-8 border-b border-white/10 pb-4">
                  <div className="flex items-center gap-3">
                    <MapPin className="w-4 h-4 text-[#D95A38]" />
                    <span className="text-[10px] font-mono uppercase tracking-widest text-[#F0EFEA]/80">
                      Global Matrix
                    </span>
                  </div>
                  <TelemetryBadge text="Syncing" active />
                </div>

                <div className="space-y-3">
                  {[
                    {
                      label: "Minimum Wage",
                      badge: LOCAL_JURISDICTIONS[jurisdictionIndex],
                    },
                    {
                      label: "Predictive Scheduling",
                      badge: "San Francisco City",
                    },
                  ].map((row, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between p-4 bg-white/[0.03] rounded-[1rem] border border-white/5"
                    >
                      <span
                        className="text-xs font-medium text-[#F0EFEA] tracking-wide"
                        style={{ fontFamily: fonts.sans }}
                      >
                        {row.label}
                      </span>
                      <span className="px-3 py-1 rounded-md bg-white/5 text-[#4ADE80] text-[9px] font-mono uppercase tracking-[0.2em] border border-[#4ADE80]/20">
                        {i === 0 ? (
                          <span className="animate-pulse">{row.badge}</span>
                        ) : (
                          row.badge
                        )}
                      </span>
                    </div>
                  ))}
                </div>
              </motion.div>
            </div>
          </div>
        </div>
      </section>

      {/* INTERVIEWER SECTION (The ASCII Focal Point) */}
      <section
        ref={manifestoRef}
        className="py-40 px-6 relative bg-[#060807] overflow-hidden rounded-[3rem] mx-4 border border-white/5 shadow-2xl"
      >
        {/* Organic Gradient Orbs */}
        <div className="absolute top-0 left-0 w-[500px] h-[500px] bg-[#4ADE80]/5 blur-[150px] rounded-full mix-blend-screen" />
        <div className="absolute bottom-0 right-0 w-[600px] h-[600px] bg-[#D95A38]/5 blur-[150px] rounded-full mix-blend-screen" />

        <div className="max-w-[1600px] mx-auto grid lg:grid-cols-2 gap-24 items-center relative z-10">
          <div className="order-2 lg:order-1 relative">
            <div className="relative aspect-square max-w-lg mx-auto bg-white/[0.02] backdrop-blur-xl rounded-[3rem] border border-white/10 flex flex-col items-center justify-center p-12 overflow-hidden group shadow-[0_0_80px_rgba(74,222,128,0.05)]">
              {/* Central ASCII Visualizer */}
              <div className="mb-12 scale-125">
                <HorizontalAsciiEntity />
              </div>

              <div className="w-full space-y-4 font-mono">
                <div className="flex justify-between text-[10px] text-[#4ADE80] uppercase tracking-widest border-t border-white/10 pt-6">
                  <span className="flex items-center gap-2">
                    <Activity size={12} /> Neural Voice Mesh
                  </span>
                  <span>Live</span>
                </div>
              </div>
            </div>
          </div>

          <div className="order-1 lg:order-2 space-y-10">
            <TelemetryBadge text="Autonomous Agent" />
            <h2
              className="text-5xl md:text-7xl font-bold tracking-tighter leading-[0.9]"
              style={{ fontFamily: fonts.sans }}
            >
              THE <br />
              <span
                className="italic text-[#F0EFEA]/50 font-light"
                style={{ fontFamily: fonts.serif }}
              >
                Interviewer.
              </span>
            </h2>
            <p className="text-[#F0EFEA]/60 text-xl font-light leading-relaxed max-w-xl">
              Replace standard screening forms with high-fidelity, autonomous
              voice agents that conduct natural conversations and extract deep
              cultural insights through latent audio analysis.
            </p>

            <div className="grid grid-cols-2 gap-8 pt-8">
              <div>
                <h4 className="font-bold text-[#F0EFEA] uppercase tracking-wider text-xs mb-2 font-mono">
                  Latent Analysis
                </h4>
                <p className="text-[#F0EFEA]/50 text-sm leading-relaxed">
                  Detects confidence and hesitation markers natively.
                </p>
              </div>
              <div>
                <h4 className="font-bold text-[#F0EFEA] uppercase tracking-wider text-xs mb-2 font-mono">
                  Dynamic Probing
                </h4>
                <p className="text-[#F0EFEA]/50 text-sm leading-relaxed">
                  Intelligent follow-up based on real-time neural processing.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* SYSTEM PROTOCOLS (Sticky Archive - High Contrast) */}
      <section ref={systemRef} className="relative mt-40">
        {/* Card 1: Obsidian */}
        <div className="system-card sticky top-0 h-screen w-full flex items-center justify-center p-6 bg-[#0A0E0C] border-t border-white/10 origin-top z-10">
          <div className="max-w-[1600px] w-full grid grid-cols-1 md:grid-cols-2 gap-24 items-center">
            <div className="space-y-8">
              <div className="text-[10px] uppercase tracking-[0.3em] text-[#D95A38] font-mono">
                Architecture // 01
              </div>
              <h2
                className="text-5xl md:text-8xl italic font-light"
                style={{ fontFamily: fonts.serif }}
              >
                ER Copilot
              </h2>
              <p className="text-xl font-light text-[#F0EFEA]/60 max-w-md">
                Your automated legal counsel. Resolves complex employee
                relations cases using your specific policy handbook.
              </p>
            </div>
            <div className="flex justify-center items-center aspect-square max-h-[500px] border border-white/5 rounded-full bg-white/[0.02] relative p-12 overflow-hidden">
              <Cpu
                size={150}
                className="text-[#4ADE80] opacity-20"
                strokeWidth={0.5}
              />
              <div className="absolute inset-0 border border-[#4ADE80]/10 rounded-full scale-75" />
            </div>
          </div>
        </div>

        {/* Card 2: Cream (High Contrast) */}
        <div className="system-card sticky top-0 h-screen w-full flex items-center justify-center p-6 bg-[#F0EFEA] text-[#0A0E0C] origin-top shadow-[0_-20px_50px_rgba(0,0,0,0.5)] z-20">
          <div className="max-w-[1600px] w-full grid grid-cols-1 md:grid-cols-2 gap-24 items-center">
            <div className="flex justify-center items-center aspect-square max-h-[500px] border border-[#0A0E0C]/10 rounded-[3rem] bg-white relative overflow-hidden order-2 md:order-1">
              <FileText
                size={150}
                className="text-[#0A0E0C]/10"
                strokeWidth={0.5}
              />
              {/* Minimalist Data visualization */}
              <div className="absolute bottom-12 left-12 right-12 h-px bg-[#0A0E0C]/10">
                <motion.div
                  animate={{ x: ["0%", "200%"] }}
                  transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
                  className="w-1/3 h-full bg-[#D95A38]"
                />
              </div>
            </div>
            <div className="space-y-8 order-1 md:order-2">
              <div className="text-[10px] uppercase tracking-[0.3em] text-[#D95A38] font-mono">
                Architecture // 02
              </div>
              <h2
                className="text-5xl md:text-8xl italic font-light"
                style={{ fontFamily: fonts.serif }}
              >
                Policy Hub
              </h2>
              <p className="text-xl font-light text-[#0A0E0C]/60 max-w-md">
                A living repository for your organization's laws. Track
                acknowledgements in real-time across biological and geographical
                limits.
              </p>
            </div>
          </div>
        </div>

        {/* Card 3: Deep Clay */}
        <div className="system-card sticky top-0 h-screen w-full flex items-center justify-center p-6 bg-[#D95A38] text-[#F0EFEA] origin-top shadow-[0_-20px_50px_rgba(0,0,0,0.5)] z-30">
          <div className="max-w-[1600px] w-full grid grid-cols-1 md:grid-cols-2 gap-24 items-center">
            <div className="space-y-8">
              <div className="text-[10px] uppercase tracking-[0.3em] text-[#0A0E0C] font-mono font-bold">
                Architecture // 03
              </div>
              <h2
                className="text-5xl md:text-8xl italic font-light"
                style={{ fontFamily: fonts.serif }}
              >
                Incident Logs
              </h2>
              <p className="text-xl font-light text-[#F0EFEA]/80 max-w-md">
                Structured workflows for safety and security. Audit-ready logs
                generated automatically from synthesized organic dialogue.
              </p>
            </div>
            <div className="flex justify-center items-center aspect-square max-h-[500px] border border-[#0A0E0C]/10 rounded-[3rem] bg-[#0A0E0C]/10 relative shadow-2xl backdrop-blur-sm">
              <Shield
                size={150}
                className="text-[#F0EFEA] opacity-50"
                strokeWidth={0.5}
              />
              <button className="absolute bottom-12 px-8 py-4 bg-[#0A0E0C] text-[#F0EFEA] rounded-full text-[10px] font-mono uppercase tracking-[0.2em] hover:bg-[#F0EFEA] hover:text-[#0A0E0C] transition-colors">
                Initialize Output
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* FOOTER */}
      <footer className="bg-[#0A0E0C] text-[#F0EFEA] pt-32 pb-12 px-6 relative z-40 border-t border-white/5">
        <div className="max-w-[1600px] mx-auto">
          <h2
            className="text-5xl md:text-8xl font-bold tracking-tighter leading-none mb-16"
            style={{ fontFamily: fonts.sans }}
          >
            INITIATE <br />
            <span
              className="italic text-[#4ADE80] font-light"
              style={{ fontFamily: fonts.serif }}
            >
              Sequence.
            </span>
          </h2>

          <div className="border-t border-white/10 pt-12 flex justify-between items-center text-[10px] font-mono uppercase tracking-[0.2em] text-[#F0EFEA]/40">
            <span>© {new Date().getFullYear()} Matcha Architecture</span>
            <div className="flex items-center gap-3">
              <span className="w-1.5 h-1.5 rounded-full bg-[#4ADE80] animate-pulse" />
              Core Systems Nominal
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default Landing;
