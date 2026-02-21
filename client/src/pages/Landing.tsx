import React, {
  memo,
  useCallback,
  useEffect,
  useRef,
  useState,
  useLayoutEffect,
  lazy,
  Suspense,
} from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import gsap from "gsap";
import ScrollTrigger from "gsap/ScrollTrigger";
import {
  MapPin,
  Activity,
  ShieldCheck,
  Database,
  Fingerprint,
} from "lucide-react";

// Lazy load the user's 3D component
const ParticleSphere = lazy(() => import("../components/ParticleSphere"));

gsap.registerPlugin(ScrollTrigger);

const fonts = {
  sans: '"Plus Jakarta Sans", "Inter", sans-serif',
  serif: '"Cormorant Garamond", serif',
  mono: '"JetBrains Mono", monospace',
};

const ER_INFERENCE_WIDTHS = [0.4, 0.8, 0.3, 0.9, 0.5, 0.7];
const POLICY_DOTS = Array.from({ length: 100 }, (_, index) => index);

const LOCAL_JURISDICTIONS = [
  "San Francisco Local",
  "West Hollywood Local",
  "Los Angeles Local",
  "Seattle Local",
];

// --- PERFORMANCE OPTIMIZED MICRO-COMPONENTS ---

// Optimized CSS Noise (Hardware Accelerated, no mix-blend-screen over full viewport)
const CinematicNoise = memo(() => (
  <div
    className="pointer-events-none fixed inset-0 z-[100] opacity-[0.03]"
    style={{
      transform: "translateZ(0)", // Force GPU layer
      backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E")`,
    }}
  />
));

// High-Performance ASCII Component (Bypasses React State for animations)
const HorizontalAsciiEntity = memo(() => {
  const preRef = useRef<HTMLPreElement>(null);
  const phaseRef = useRef(0);

  useEffect(() => {
    let animationFrameId: number;
    let lastTime = performance.now();
    const fps = 15; // Limit FPS to save CPU
    const interval = 1000 / fps;

    const generateLines = (phase: number) => {
      let result = "";
      for (let i = 0; i < 24; i++) {
        const offset = Math.sin((i + phase * 0.5) * 0.2) * 10;
        const width = Math.max(10, 30 + Math.sin((i - phase * 0.3) * 0.4) * 20);
        const char = width > 40 ? "━" : width > 25 ? "─" : "-";
        const padding = " ".repeat(Math.max(0, Math.floor(20 + offset)));
        result += padding + char.repeat(Math.floor(width)) + "\n";
      }
      return result;
    };

    const animate = (time: number) => {
      animationFrameId = requestAnimationFrame(animate);
      const deltaTime = time - lastTime;

      if (deltaTime > interval) {
        lastTime = time - (deltaTime % interval);
        phaseRef.current += 1;
        if (preRef.current) {
          preRef.current.textContent = generateLines(phaseRef.current);
        }
      }
    };

    animationFrameId = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animationFrameId);
  }, []);

  return (
    <div className="relative group">
      <div
        className="absolute inset-0 bg-[#4ADE80] opacity-10 blur-[40px] rounded-full group-hover:opacity-20 transition-opacity duration-1000"
        style={{ transform: "translateZ(0)" }}
      />
      <pre
        ref={preRef}
        className="relative z-10 font-mono text-[10px] leading-[0.6] tracking-tighter text-[#4ADE80] select-none whitespace-pre"
        style={{
          textShadow: "0 0 10px rgba(74, 222, 128, 0.4)",
          transform: "translateZ(0)",
        }}
      />
      <div className="absolute top-0 right-0 text-[#F0EFEA]/30 text-[8px] font-mono uppercase tracking-[0.3em]">
        Neural Entity
      </div>
    </div>
  );
});

interface TelemetryBadgeProps {
  text: string;
  active?: boolean;
}

// Dynamic Telemetry Badge
const TelemetryBadge = memo(function TelemetryBadge({
  text,
  active = false,
}: TelemetryBadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-2 px-3 py-1 rounded-full border text-[9px] font-mono uppercase tracking-widest transition-colors duration-500
      ${active ? "border-[#4ADE80]/30 bg-[#4ADE80]/10 text-[#4ADE80]" : "border-[#F0EFEA]/10 bg-[#F0EFEA]/5 text-[#F0EFEA]/60"}`}
    >
      {active && (
        <span className="w-1.5 h-1.5 bg-[#4ADE80] rounded-full animate-pulse shadow-[0_0_8px_#4ADE80]" />
      )}
      {text}
    </span>
  );
});

// --- ARCHITECTURE MICRO-INTERFACES (Replaces static icons) ---

const ERInferenceEngine = memo(() => (
  <div className="w-full h-full flex flex-col justify-center gap-4 p-8">
    <div className="flex justify-between text-[8px] font-mono text-[#4ADE80]/50 uppercase tracking-widest mb-4">
      <span>Neural Map</span>
      <span className="animate-pulse">Processing</span>
    </div>
    {ER_INFERENCE_WIDTHS.map((width, i) => (
      <div
        key={i}
        className="h-1 w-full bg-white/5 rounded-full overflow-hidden"
      >
        <motion.div
          initial={{ x: "-100%" }}
          animate={{ x: "200%" }}
          transition={{
            duration: 2 + i * 0.5,
            repeat: Infinity,
            ease: "linear",
            delay: i * 0.2,
          }}
          className="h-full bg-[#4ADE80] shadow-[0_0_10px_#4ADE80]"
          style={{ width: `${width * 100}%` }}
        />
      </div>
    ))}
    <Database
      size={24}
      className="text-[#4ADE80]/20 absolute bottom-8 right-8"
    />
  </div>
));

const PolicyMatrixScanner = memo(() => {
  return (
    <div className="w-full h-full relative p-8 flex items-center justify-center overflow-hidden">
      <div className="grid grid-cols-10 gap-3 relative z-10">
        {POLICY_DOTS.map((dotIndex) => (
          <div
            key={dotIndex}
            className="w-1.5 h-1.5 rounded-full bg-[#0A0E0C]/10 transition-colors duration-500 hover:bg-[#D95A38]"
          />
        ))}
      </div>
      {/* Scanner Line */}
      <motion.div
        animate={{ y: ["-100%", "500%"] }}
        transition={{ duration: 4, repeat: Infinity, ease: "linear" }}
        className="absolute left-0 right-0 h-[2px] bg-[#D95A38] shadow-[0_0_30px_#D95A38] z-20"
      />
      <Fingerprint
        size={24}
        className="text-[#0A0E0C]/10 absolute bottom-8 left-8"
      />
    </div>
  );
});

const IncidentAuditRing = memo(() => (
  <div className="w-full h-full relative flex items-center justify-center">
    <div className="absolute inset-0 border border-[#F0EFEA]/10 rounded-full scale-[0.6] animate-[ping_4s_cubic-bezier(0,0,0.2,1)_infinite]" />
    <div className="absolute inset-0 border border-[#F0EFEA]/20 rounded-full scale-[0.4] animate-[spin_10s_linear_infinite] border-t-transparent" />
    <div className="absolute inset-0 border border-[#F0EFEA]/30 rounded-full scale-[0.3] animate-[spin_7s_linear_infinite_reverse] border-b-transparent" />
    <div className="w-4 h-4 bg-[#F0EFEA] rounded-full shadow-[0_0_20px_#F0EFEA] animate-pulse relative z-10" />
    <ShieldCheck
      size={24}
      className="text-[#F0EFEA]/30 absolute top-8 right-8"
    />
  </div>
));

const JurisdictionRows = memo(function JurisdictionRows() {
  const [jurisdictionIndex, setJurisdictionIndex] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setJurisdictionIndex((prev) => (prev + 1) % LOCAL_JURISDICTIONS.length);
    }, 4000);

    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between p-4 bg-white/[0.03] rounded-[1rem] border border-white/5">
        <span
          className="text-xs font-medium text-[#F0EFEA] tracking-wide"
          style={{ fontFamily: fonts.sans }}
        >
          Minimum Wage
        </span>
        <span className="px-3 py-1 rounded-md bg-white/5 text-[#4ADE80] text-[9px] font-mono uppercase tracking-[0.2em] border border-[#4ADE80]/20">
          {LOCAL_JURISDICTIONS[jurisdictionIndex]}
        </span>
      </div>
      <div className="flex items-center justify-between p-4 bg-white/[0.03] rounded-[1rem] border border-white/5">
        <span
          className="text-xs font-medium text-[#F0EFEA] tracking-wide"
          style={{ fontFamily: fonts.sans }}
        >
          Predictive Scheduling
        </span>
        <span className="px-3 py-1 rounded-md bg-white/5 text-[#4ADE80] text-[9px] font-mono uppercase tracking-[0.2em] border border-[#4ADE80]/20">
          San Francisco City
        </span>
      </div>
    </div>
  );
});

// --- MAIN LANDING PAGE ---

export function Landing() {
  const containerRef = useRef<HTMLDivElement>(null);
  const manifestoRef = useRef<HTMLDivElement>(null);
  const systemRef = useRef<HTMLDivElement>(null);

  const [scrolled, setScrolled] = useState(false);
  const scrolledRef = useRef(false);

  useEffect(() => {
    let ticking = false;
    let frameId = 0;
    const updateScrolled = () => {
      const nextScrolled = window.scrollY > 50;
      if (nextScrolled !== scrolledRef.current) {
        scrolledRef.current = nextScrolled;
        setScrolled(nextScrolled);
      }
      ticking = false;
    };

    const handleScroll = () => {
      if (!ticking) {
        frameId = window.requestAnimationFrame(updateScrolled);
        ticking = true;
      }
    };

    updateScrolled();
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      if (frameId) {
        window.cancelAnimationFrame(frameId);
      }
      window.removeEventListener("scroll", handleScroll);
    };
  }, []);

  useLayoutEffect(() => {
    const ctx = gsap.context(() => {
      // Hero Text Fade Up
      gsap.from(".reveal-text", {
        y: 60,
        opacity: 0,
        stagger: 0.1,
        duration: 1.2,
        ease: "power3.out",
        delay: 0.1,
      });

      // Parallax optimized (using GSAP FastScroll/Transform)
      gsap.utils.toArray(".parallax-bg").forEach((bg: any) => {
        gsap.to(bg, {
          yPercent: 15,
          ease: "none",
          scrollTrigger: {
            trigger: bg.parentElement,
            start: "top bottom",
            end: "bottom top",
            scrub: true,
          },
        });
      });

      // Sticky Archive Animation (Removed blur for performance, using just opacity/scale)
      const cards = gsap.utils.toArray(".system-card");
      cards.forEach((card: any, i: number) => {
        if (i === cards.length - 1) return;
        gsap.to(card, {
          scale: 0.95,
          opacity: 0.3, // Optimization: No CSS filter blur
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

  const scrollTo = useCallback((ref: React.RefObject<HTMLDivElement | null>) => {
    ref.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  return (
    <div
      ref={containerRef}
      className="bg-[#0A0E0C] text-[#F0EFEA] selection:bg-[#4ADE80] selection:text-[#0A0E0C] overflow-x-hidden min-h-screen"
    >
      <CinematicNoise />

      {/* NAVBAR */}
      <nav className="fixed top-6 left-1/2 -translate-x-1/2 z-50 w-[92%] max-w-[1600px] pointer-events-none">
        <div
          className={`pointer-events-auto flex items-center justify-between px-6 py-4 rounded-[2rem] transition-all duration-500 border ${
            scrolled
              ? "bg-[#0A0E0C]/80 backdrop-blur-md border-[#F0EFEA]/10 shadow-2xl"
              : "bg-transparent border-transparent"
          }`}
        >
          <Link to="/" className="flex items-center gap-3 group">
            <div className="w-8 h-8 rounded-full border border-[#F0EFEA]/20 flex items-center justify-center overflow-hidden bg-[#0A0E0C]">
              <div className="w-full h-full bg-[#4ADE80] opacity-0 group-hover:opacity-30 transition-opacity duration-300" />
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
              System
            </span>
            <span className="text-[#F0EFEA]/35 cursor-default">
              Pricing
            </span>
            <Link to="/terms" className="hover:text-[#4ADE80] transition-colors">
              Terms
            </Link>
          </div>
          <Link
            to="/login"
            className="px-6 py-2.5 rounded-full border border-[#F0EFEA]/20 text-[10px] font-mono uppercase tracking-[0.2em] hover:bg-[#F0EFEA] hover:text-[#0A0E0C] transition-colors"
          >
            Login
          </Link>
        </div>
      </nav>

      {/* HERO SECTION */}
      <section className="relative min-h-screen flex flex-col justify-center px-6 md:px-16 overflow-hidden">
        <div className="absolute inset-0 z-0 overflow-hidden pointer-events-none">
          <div
            className="parallax-bg absolute -inset-[10%] bg-cover bg-center opacity-[0.18]"
            style={{
              backgroundImage: `url('https://images.unsplash.com/photo-1419242902214-272b3f66ee7a?q=80&w=3500&auto=format&fit=crop')`,
            }}
          />
          <div className="absolute inset-0 bg-gradient-to-t from-[#0A0E0C] via-[#0A0E0C]/80 to-transparent" />
          <div className="absolute inset-0 bg-gradient-to-r from-[#0A0E0C] via-transparent to-transparent" />
        </div>

        <div className="relative z-20 w-full max-w-[1600px] mx-auto grid lg:grid-cols-2 gap-12 items-center">
          <div className="flex flex-col items-start relative z-10 pt-20">
            <TelemetryBadge text="Core System v2.4 Online" active />
            <h1 className="mt-8 leading-[0.85] tracking-tighter mix-blend-lighten">
              <span
                className="reveal-text block text-[4rem] md:text-[6.5rem] font-bold uppercase"
                style={{
                  fontFamily: fonts.sans,
                  willChange: "transform, opacity",
                }}
              >
                Workforce
              </span>
              <span
                className="reveal-text block text-[5rem] md:text-[7.5rem] italic font-light text-[#D95A38]"
                style={{
                  fontFamily: fonts.serif,
                  willChange: "transform, opacity",
                }}
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

          <div
            className="relative h-[50vh] lg:h-[80vh] w-full flex items-center justify-center z-0 mt-12 lg:mt-0"
            style={{ transform: "translateZ(0)" }}
          >
            <Suspense
              fallback={
                <div className="text-[#4ADE80] font-mono text-[10px] uppercase tracking-widest animate-pulse flex flex-col items-center gap-4">
                  <div className="w-8 h-8 border border-[#4ADE80] rounded-full border-t-transparent animate-spin" />
                  Initializing Neural Sphere...
                </div>
              }
            >
              <div className="absolute inset-0 bg-[#4ADE80]/5 blur-[100px] rounded-full mix-blend-screen pointer-events-none" />
              <ParticleSphere
                className="w-full h-full scale-110 lg:scale-125"
                showCityMarkers
              />
            </Suspense>
          </div>
        </div>
      </section>

      {/* COMPLIANCE / PRECISION MICRO-UI */}
      <section className="py-40 px-6 relative border-t border-white/5 bg-[#0A0E0C]">
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
              employee endpoint natively.
            </p>
          </div>

          <div className="relative z-10 space-y-6">
            <div className="bg-[#0A0E0C] rounded-[2rem] border border-white/10 p-8 shadow-[0_0_50px_rgba(0,0,0,0.5)] overflow-hidden relative">
              <motion.div
                animate={{ top: ["-10%", "110%"] }}
                transition={{ duration: 4, repeat: Infinity, ease: "linear" }}
                className="absolute left-0 right-0 h-[1px] bg-[#4ADE80]/30 shadow-[0_0_20px_#4ADE80] z-30"
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
              <JurisdictionRows />
            </div>
          </div>
        </div>
      </section>

      {/* INTERVIEWER SECTION */}
      <section
        ref={manifestoRef}
        className="py-40 px-6 relative bg-[#060807] overflow-hidden rounded-[3rem] mx-4 border border-white/5 shadow-2xl"
        style={{ transform: "translateZ(0)" }}
      >
        <div className="absolute top-0 left-0 w-[500px] h-[500px] bg-[#4ADE80]/5 blur-[120px] rounded-full mix-blend-screen pointer-events-none" />

        <div className="max-w-[1600px] mx-auto grid lg:grid-cols-2 gap-24 items-center relative z-10">
          <div className="order-2 lg:order-1 relative">
            <div className="relative aspect-square max-w-lg mx-auto bg-white/[0.02] backdrop-blur-xl rounded-[3rem] border border-white/10 flex flex-col items-center justify-center p-12 overflow-hidden shadow-[0_0_80px_rgba(74,222,128,0.05)]">
              <div className="mb-12 scale-125">
                <HorizontalAsciiEntity />
              </div>
              <div className="w-full font-mono border-t border-white/10 pt-6">
                <div className="flex justify-between text-[10px] text-[#4ADE80] uppercase tracking-widest">
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

      {/* SYSTEM PROTOCOLS (Sticky Archive - High Contrast & Dynamic Micro UIs) */}
      <section ref={systemRef} className="relative mt-40">
        {/* Card 1: Obsidian (ER Copilot) */}
        <div className="system-card sticky top-0 h-screen w-full flex items-center justify-center p-6 bg-[#0A0E0C] border-t border-white/10 origin-top z-10 will-change-transform">
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
                relations cases using your specific policy handbook and active
                telemetry.
              </p>
            </div>
            {/* Dynamic Interactive Artifact */}
            <div className="aspect-square max-h-[500px] border border-white/5 rounded-[3rem] bg-white/[0.02] relative overflow-hidden backdrop-blur-md">
              <ERInferenceEngine />
            </div>
          </div>
        </div>

        {/* Card 2: Cream (Policy Hub) */}
        <div className="system-card sticky top-0 h-screen w-full flex items-center justify-center p-6 bg-[#F0EFEA] text-[#0A0E0C] origin-top shadow-[0_-20px_50px_rgba(0,0,0,0.5)] z-20 will-change-transform">
          <div className="max-w-[1600px] w-full grid grid-cols-1 md:grid-cols-2 gap-24 items-center">
            {/* Dynamic Interactive Artifact */}
            <div className="aspect-square max-h-[500px] border border-[#0A0E0C]/10 rounded-[3rem] bg-white relative overflow-hidden order-2 md:order-1 shadow-inner">
              <PolicyMatrixScanner />
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

        {/* Card 3: Deep Clay (Incident Logs) */}
        <div className="system-card sticky top-0 h-screen w-full flex items-center justify-center p-6 bg-[#D95A38] text-[#F0EFEA] origin-top shadow-[0_-20px_50px_rgba(0,0,0,0.5)] z-30 will-change-transform">
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
              <p className="text-xl font-light text-[#F0EFEA]/90 max-w-md">
                Structured workflows for safety and security. Audit-ready logs
                generated automatically from synthesized organic dialogue.
              </p>
            </div>
            {/* Dynamic Interactive Artifact */}
            <div className="aspect-square max-h-[500px] border border-[#0A0E0C]/10 rounded-[3rem] bg-[#0A0E0C]/10 relative shadow-2xl backdrop-blur-md overflow-hidden flex flex-col">
              <div className="flex-1">
                <IncidentAuditRing />
              </div>
              <div className="p-8 border-t border-[#0A0E0C]/10">
                <button className="w-full py-4 bg-[#0A0E0C] text-[#F0EFEA] rounded-full text-[10px] font-mono uppercase tracking-[0.2em] hover:bg-[#F0EFEA] hover:text-[#0A0E0C] transition-colors shadow-lg">
                  Initialize Output
                </button>
              </div>
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
              <span className="w-1.5 h-1.5 rounded-full bg-[#4ADE80] animate-[pulse_2s_linear_infinite]" />
              Core Systems Nominal
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default Landing;
