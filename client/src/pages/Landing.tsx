import React, { useEffect, useRef, useState, useLayoutEffect } from "react";
import { Link } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import gsap from "gsap";
import ScrollTrigger from "gsap/ScrollTrigger";
import {
  ArrowUpRight,
  Terminal,
  Shield,
  FileText,
  Users,
  Cpu,
  MapPin,
  X,
  Send,
  Sparkles,
  Zap,
} from "lucide-react";

gsap.registerPlugin(ScrollTrigger);

// --- DESIGN TOKENS ---
const theme = {
  moss: "#2E4036",
  clay: "#CC5833",
  cream: "#F2F0E9",
  charcoal: "#1A1A1A",
};

const fonts = {
  sans: '"Outfit", "Plus Jakarta Sans", sans-serif',
  serif: '"Cormorant Garamond", serif',
  mono: '"JetBrains Mono", monospace',
};

// --- DATA ---
const LOCAL_JURISDICTIONS = [
  "San Francisco Local",
  "West Hollywood Local",
  "Los Angeles Local",
  "Berkeley Local",
  "Emeryville Local",
  "Seattle Local",
];

const WAVEFORM_FRAMES = [
  String.raw`
      .----------------------------------------.
      |   MATCHA VOICE SIGNAL :: REAL-TIME     |
      |----------------------------------------|
      |                                        |
      |   __      __        __      __       _ |
      | _/  \____/  \__/\__/  \____/  \__/\_/ \|
      |                                        |
      |   gain:+4dB   mode:screening   LIVE    |
      '----------------------------------------'
`,
  String.raw`
      .----------------------------------------.
      |   MATCHA VOICE SIGNAL :: REAL-TIME     |
      |----------------------------------------|
      |                                        |
      |      __        __        __        __  |
      | ____/  \__/\__/  \__/\__/  \__/\__/  \_|
      |                                        |
      |   gain:+4dB   mode:screening   LIVE    |
      '----------------------------------------'
`,
  String.raw`
      .----------------------------------------.
      |   MATCHA VOICE SIGNAL :: REAL-TIME     |
      |----------------------------------------|
      |                                        |
      |  _    _      _    _      _    _      _ |
      | _/ \__/ \____/ \__/ \____/ \__/ \____/ \|
      |                                        |
      |   gain:+4dB   mode:screening   LIVE    |
      '----------------------------------------'
`,
];

const WAVEFORM_SEQUENCE = [0, 1, 2, 1];

// --- MICRO-COMPONENTS ---

const GlobalNoise = () => (
  <div
    className="pointer-events-none fixed inset-0 z-[100] opacity-[0.05] mix-blend-overlay"
    style={{
      backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E")`,
    }}
  />
);

const Marquee = ({ children }: { children: React.ReactNode }) => (
  <div className="relative flex overflow-hidden border-y border-[#1A1A1A]/10 bg-[#2E4036]/5 py-6">
    <div className="animate-marquee whitespace-nowrap flex gap-8">
      {[...Array(4)].map((_, i) => (
        <span
          key={i}
          className="text-4xl font-light uppercase tracking-widest text-[#2E4036] opacity-40"
          style={{ fontFamily: fonts.sans }}
        >
          {children}
        </span>
      ))}
    </div>
    <div className="absolute top-0 flex animate-marquee2 whitespace-nowrap gap-8 pt-6">
      {[...Array(4)].map((_, i) => (
        <span
          key={i}
          className="text-4xl font-light uppercase tracking-widest text-[#2E4036] opacity-40"
          style={{ fontFamily: fonts.sans }}
        >
          {children}
        </span>
      ))}
    </div>
  </div>
);

const TypewriterBadge = ({ text }: { text: string }) => {
  const [displayText, setDisplayText] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    let timeout: NodeJS.Timeout;
    const type = () => {
      const fullText = text;
      if (!isDeleting) {
        setDisplayText(fullText.substring(0, displayText.length + 1));
        if (displayText === fullText) {
          timeout = setTimeout(() => setIsDeleting(true), 2000);
        } else {
          timeout = setTimeout(type, 50);
        }
      } else {
        setDisplayText(fullText.substring(0, displayText.length - 1));
        if (displayText === "") {
          setIsDeleting(false);
        } else {
          timeout = setTimeout(type, 30);
        }
      }
    };
    timeout = setTimeout(type, isDeleting ? 30 : 50);
    return () => clearTimeout(timeout);
  }, [displayText, isDeleting, text]);

  useEffect(() => {
    setIsDeleting(false);
    setDisplayText("");
  }, [text]);

  return (
    <span className="inline-flex items-center">
      {displayText}
      <motion.span
        animate={{ opacity: [1, 0] }}
        transition={{ duration: 0.5, repeat: Infinity, ease: "linear" }}
        className="w-1 h-3 bg-[#CC5833] ml-0.5"
      />
    </span>
  );
};

const AsciiWaveform = () => {
  const [sequenceIndex, setSequenceIndex] = useState(0);

  useEffect(() => {
    const frameTimer = setInterval(() => {
      setSequenceIndex((prev) => (prev + 1) % WAVEFORM_SEQUENCE.length);
    }, 150);
    return () => clearInterval(frameTimer);
  }, []);

  const frameIndex = WAVEFORM_SEQUENCE[sequenceIndex] ?? 0;

  return (
    <div className="font-mono text-[#CC5833] leading-none select-none">
      <motion.pre
        animate={{ opacity: [0.7, 1, 0.78] }}
        transition={{ duration: 0.32, repeat: Infinity, ease: "linear" }}
        className="text-[9px] md:text-[10px] leading-[0.95] whitespace-pre"
        style={{ fontFamily: fonts.mono }}
      >
        {WAVEFORM_FRAMES[frameIndex]}
      </motion.pre>
    </div>
  );
};

function ContactModal({
  isOpen,
  onClose,
}: {
  isOpen: boolean;
  onClose: () => void;
}) {
  const [formData, setFormData] = useState({
    name: "",
    email: "",
    message: "",
  });
  const [sent, setSent] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const mailtoUrl = `mailto:aaron@hey-matcha.com?subject=Matcha Inquiry from ${formData.name}&body=${formData.message}%0D%0A%0D%0AFrom: ${formData.email}`;
    window.location.href = mailtoUrl;
    setSent(true);
    setTimeout(() => {
      setSent(false);
      onClose();
    }, 2000);
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-6">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="absolute inset-0 bg-[#1A1A1A]/80 backdrop-blur-md"
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            className="relative w-full max-w-lg bg-[#F2F0E9] text-[#1A1A1A] rounded-[2rem] p-8 md:p-12 shadow-2xl"
          >
            <button
              onClick={onClose}
              className="absolute top-6 right-6 text-[#1A1A1A]/50 hover:text-[#CC5833] transition-colors"
            >
              <X className="w-6 h-6" />
            </button>

            {sent ? (
              <div className="py-12 text-center space-y-4">
                <div className="w-16 h-16 bg-[#2E4036]/10 rounded-full flex items-center justify-center mx-auto mb-6">
                  <Send className="w-8 h-8 text-[#2E4036]" />
                </div>
                <h3
                  className="text-2xl font-bold uppercase tracking-tighter"
                  style={{ fontFamily: fonts.sans }}
                >
                  Request Received
                </h3>
                <p className="text-[#1A1A1A]/60 font-mono text-sm uppercase tracking-widest leading-relaxed">
                  Redirecting to client...
                </p>
              </div>
            ) : (
              <div className="space-y-8">
                <div>
                  <h3
                    className="text-3xl font-bold uppercase tracking-tighter mb-2"
                    style={{ fontFamily: fonts.sans }}
                  >
                    Request Pricing
                  </h3>
                  <p className="text-[#CC5833] font-mono text-[10px] uppercase tracking-[0.2em]">
                    System Initialization
                  </p>
                </div>

                <form onSubmit={handleSubmit} className="space-y-6">
                  <div className="space-y-2">
                    <label className="text-[10px] font-mono uppercase tracking-widest text-[#1A1A1A]/60 ml-1">
                      Full Name
                    </label>
                    <input
                      required
                      type="text"
                      value={formData.name}
                      onChange={(e) =>
                        setFormData({ ...formData, name: e.target.value })
                      }
                      className="w-full bg-white border border-[#1A1A1A]/10 rounded-xl px-4 py-3 text-sm focus:border-[#2E4036] outline-none transition-colors"
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-[10px] font-mono uppercase tracking-widest text-[#1A1A1A]/60 ml-1">
                      Work Email
                    </label>
                    <input
                      required
                      type="email"
                      value={formData.email}
                      onChange={(e) =>
                        setFormData({ ...formData, email: e.target.value })
                      }
                      className="w-full bg-white border border-[#1A1A1A]/10 rounded-xl px-4 py-3 text-sm focus:border-[#2E4036] outline-none transition-colors"
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-[10px] font-mono uppercase tracking-widest text-[#1A1A1A]/60 ml-1">
                      Project Requirements
                    </label>
                    <textarea
                      required
                      rows={4}
                      value={formData.message}
                      onChange={(e) =>
                        setFormData({ ...formData, message: e.target.value })
                      }
                      className="w-full bg-white border border-[#1A1A1A]/10 rounded-xl px-4 py-3 text-sm focus:border-[#2E4036] outline-none transition-colors resize-none"
                    />
                  </div>
                  <button
                    type="submit"
                    className="w-full bg-[#2E4036] text-[#F2F0E9] rounded-xl py-4 font-mono text-sm uppercase tracking-[0.2em] font-bold hover:bg-[#1A1A1A] transition-all hover:scale-[1.02]"
                  >
                    Send Request
                  </button>
                </form>
              </div>
            )}
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}

// --- MAIN LANDING PAGE ---

export function Landing() {
  const containerRef = useRef<HTMLDivElement>(null);
  const manifestoRef = useRef<HTMLDivElement>(null);
  const systemRef = useRef<HTMLDivElement>(null);

  const [jurisdictionIndex, setJurisdictionIndex] = useState(0);
  const [isContactOpen, setIsContactOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const timer = setInterval(() => {
      setJurisdictionIndex((prev) => (prev + 1) % LOCAL_JURISDICTIONS.length);
    }, 5000);

    const handleScroll = () => setScrolled(window.scrollY > 50);
    window.addEventListener("scroll", handleScroll);

    return () => {
      clearInterval(timer);
      window.removeEventListener("scroll", handleScroll);
    };
  }, []);

  useLayoutEffect(() => {
    const ctx = gsap.context(() => {
      // Hero Text Fade Up
      gsap.from(".hero-part", {
        y: 60,
        opacity: 0,
        stagger: 0.15,
        duration: 1.2,
        ease: "power4.out",
        delay: 0.2,
      });

      // Manifesto Parallax & Reveal
      gsap.fromTo(
        ".phil-bg",
        { yPercent: -15 },
        {
          yPercent: 15,
          ease: "none",
          scrollTrigger: {
            trigger: manifestoRef.current,
            start: "top bottom",
            end: "bottom top",
            scrub: true,
          },
        },
      );

      gsap.from(".phil-text", {
        y: 40,
        opacity: 0,
        stagger: 0.2,
        duration: 1,
        ease: "power3.out",
        scrollTrigger: { trigger: manifestoRef.current, start: "top 60%" },
      });

      // GSAP Sticky Stacking Archive (System Modules)
      const cards = gsap.utils.toArray(".system-card");
      cards.forEach((card: any, i: number) => {
        if (i === cards.length - 1) return; // Skip last card
        gsap.to(card, {
          scale: 0.9,
          filter: "blur(10px)",
          opacity: 0.5,
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
      className="bg-[#F2F0E9] text-[#1A1A1A] font-sans selection:bg-[#CC5833] selection:text-[#F2F0E9] overflow-x-hidden"
    >
      <GlobalNoise />
      <ContactModal
        isOpen={isContactOpen}
        onClose={() => setIsContactOpen(false)}
      />

      {/* NAVBAR (The Floating Island) */}
      <nav className="fixed top-6 left-1/2 -translate-x-1/2 z-50 w-[95%] max-w-[1800px]">
        <div
          className={`flex items-center justify-between px-6 md:px-8 py-4 rounded-full transition-all duration-700 ${
            scrolled
              ? "bg-white/70 backdrop-blur-lg border border-[#2E4036]/10 text-[#1A1A1A] shadow-lg"
              : "bg-transparent text-[#F2F0E9]"
          }`}
        >
          <Link to="/" className="flex items-center gap-3 group">
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center transition-colors ${scrolled ? "bg-[#2E4036]" : "bg-[#F2F0E9]"}`}
            >
              <div
                className={`w-3 h-3 rounded-full group-hover:scale-0 transition-transform duration-500 ${scrolled ? "bg-[#F2F0E9]" : "bg-[#1A1A1A]"}`}
              />
            </div>
            <span className="font-sans text-lg font-bold tracking-tight uppercase">
              Matcha
            </span>
          </Link>
          <div className="hidden md:flex gap-8 text-xs font-mono uppercase tracking-widest">
            <span
              onClick={() => scrollTo(manifestoRef)}
              className="hover:text-[#CC5833] cursor-pointer transition-colors"
            >
              Manifesto
            </span>
            <span
              onClick={() => scrollTo(systemRef)}
              className="hover:text-[#CC5833] cursor-pointer transition-colors"
            >
              System
            </span>
            <span
              onClick={() => setIsContactOpen(true)}
              className="hover:text-[#CC5833] cursor-pointer transition-colors"
            >
              Pricing
            </span>
          </div>
          <Link
            to="/login"
            className={`px-6 py-3 rounded-full text-xs font-mono uppercase tracking-widest font-bold transition-transform hover:scale-105 ${
              scrolled
                ? "bg-[#CC5833] text-[#F2F0E9]"
                : "bg-[#F2F0E9] text-[#1A1A1A]"
            }`}
          >
            Login
          </Link>
        </div>
      </nav>

      {/* HERO SECTION (Nature is the Algorithm style) */}
      <section className="relative min-h-screen flex flex-col justify-end pb-24 px-6 md:px-16 overflow-hidden">
        {/* Moody Architectural/Tech Abstract Background */}
        <div
          className="absolute inset-0 z-0 bg-cover bg-center"
          style={{
            backgroundImage: `url('https://images.unsplash.com/photo-1550684848-fac1c5b4e853?q=80&w=3500&auto=format&fit=crop')`,
          }}
        />
        <div className="absolute inset-0 z-10 bg-gradient-to-t from-[#1A1A1A] via-[#2E4036]/90 to-[#1A1A1A]/40 mix-blend-multiply" />

        <div className="relative z-20 w-full max-w-[1800px] mx-auto flex flex-col items-start text-[#F2F0E9]">
          <div className="hero-part inline-flex items-center gap-3 px-4 py-2 rounded-full mb-8 bg-white/10 backdrop-blur-md border border-white/20">
            <span className="w-2 h-2 bg-[#CC5833] rounded-full animate-pulse" />
            <span className="text-[10px] font-mono uppercase tracking-widest">
              System v2.4 Live
            </span>
          </div>

          <h1 className="leading-[0.85] tracking-tighter w-full">
            <span
              className="hero-part block text-[4rem] md:text-[7rem] font-bold uppercase"
              style={{ fontFamily: fonts.sans }}
            >
              Workforce
            </span>
            <span
              className="hero-part block text-[5rem] md:text-[9rem] italic font-light text-[#CC5833]"
              style={{ fontFamily: fonts.serif }}
            >
              Intelligence.
            </span>
          </h1>

          <div className="hero-part flex flex-col md:flex-row gap-8 items-start md:items-center max-w-2xl mt-8">
            <p
              className="text-[#F2F0E9]/70 text-lg md:text-xl leading-relaxed font-light"
              style={{ fontFamily: fonts.sans }}
            >
              The operating system for modern workforce management. <br />
              Stripped of administrative noise. Engineered for organizational
              clarity.
            </p>
          </div>
        </div>
      </section>

      {/* COMPLIANCE SECTION (Precision Micro-UI logic) */}
      <section className="py-32 px-6 bg-[#F2F0E9] relative overflow-hidden">
        <div className="max-w-[1800px] mx-auto grid lg:grid-cols-2 gap-24 items-center relative z-10">
          <div className="space-y-12">
            <div>
              <h2
                className="text-5xl md:text-7xl font-bold tracking-tighter leading-[0.9] mb-8 text-[#1A1A1A]"
                style={{ fontFamily: fonts.sans }}
              >
                KNOW EXACTLY <br />
                WHICH LAW APPLIES <br />
                <span
                  className="italic text-[#CC5833] font-light"
                  style={{ fontFamily: fonts.serif }}
                >
                  — At Every Location.
                </span>
              </h2>
              <p className="text-[#1A1A1A]/70 text-xl leading-relaxed max-w-xl font-light">
                Matcha monitors labor laws across city, county, and state levels
                — deploying the exact governance rule for every single employee
                endpoint.
              </p>
            </div>

            <div className="space-y-8 border-t border-[#1A1A1A]/10 pt-8">
              {[
                {
                  title: "Hierarchical Deference",
                  desc: "Knows when municipalities defer to broader state or county level statutes natively.",
                },
                {
                  title: "Beneficial Application",
                  desc: "When rules conflict, the system autonomously applies the regulation most beneficial to the employee.",
                },
              ].map((point, i) => (
                <div key={i} className="flex gap-6">
                  <div className="text-[#CC5833] font-mono text-sm mt-1">
                    0{i + 1}
                  </div>
                  <div className="space-y-2">
                    <h4
                      className="font-bold text-[#1A1A1A] uppercase tracking-tight"
                      style={{ fontFamily: fonts.sans }}
                    >
                      {point.title}
                    </h4>
                    <p className="text-sm text-[#1A1A1A]/60 leading-relaxed max-w-md">
                      {point.desc}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="relative">
            {/* Clinical Boutique styling for the Mock UI Cards */}
            <div className="space-y-6 relative z-10">
              {/* Card 1 */}
              <motion.div
                animate={{ y: [0, -10, 0] }}
                transition={{
                  duration: 6,
                  repeat: Infinity,
                  ease: "easeInOut",
                }}
                className="bg-[#1A1A1A] rounded-[2rem] border border-[#2E4036]/20 p-8 shadow-2xl relative overflow-hidden"
              >
                <div className="flex items-center justify-between mb-6 pb-4 border-b border-white/10">
                  <div className="flex items-center gap-3">
                    <MapPin className="w-4 h-4 text-[#CC5833]" />
                    <span className="text-xs font-mono uppercase tracking-widest text-[#F2F0E9]/70">
                      Global Telemetry
                    </span>
                  </div>
                  <div className="px-3 py-1 rounded-full bg-[#2E4036]/40 text-[#F2F0E9] text-[10px] font-mono uppercase flex items-center gap-2 border border-[#2E4036]">
                    <span className="w-1.5 h-1.5 rounded-full bg-[#CC5833] animate-pulse" />{" "}
                    Active
                  </div>
                </div>

                <div className="space-y-2">
                  {[
                    {
                      label: "Minimum Wage",
                      badge: LOCAL_JURISDICTIONS[jurisdictionIndex],
                      isDynamic: true,
                    },
                    { label: "Sick Leave", badge: "California Code" },
                    { label: "Overtime", badge: "Federal Alignment" },
                  ].map((row, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between p-4 bg-white/5 rounded-xl border border-white/5"
                    >
                      <span
                        className="text-xs font-bold text-[#F2F0E9] uppercase tracking-wider"
                        style={{ fontFamily: fonts.sans }}
                      >
                        {row.label}
                      </span>
                      <span className="px-3 py-1 rounded-md bg-[#CC5833]/10 text-[#CC5833] text-[10px] font-mono uppercase tracking-wider border border-[#CC5833]/20">
                        {row.isDynamic ? (
                          <TypewriterBadge text={row.badge} />
                        ) : (
                          row.badge
                        )}
                      </span>
                    </div>
                  ))}
                </div>
              </motion.div>

              {/* Card 2 */}
              <motion.div
                animate={{ y: [0, 10, 0] }}
                transition={{
                  duration: 7,
                  repeat: Infinity,
                  ease: "easeInOut",
                  delay: 1,
                }}
                className="bg-[#2E4036] rounded-[2rem] border border-white/10 p-8 shadow-2xl ml-12 relative overflow-hidden"
              >
                <div className="flex items-center justify-between mb-6 pb-4 border-b border-white/10">
                  <div className="flex items-center gap-3">
                    <MapPin className="w-4 h-4 text-[#F2F0E9]/50" />
                    <span className="text-xs font-mono uppercase tracking-widest text-[#F2F0E9]">
                      Del Mar, CA
                    </span>
                  </div>
                </div>
                <div className="flex items-center justify-between p-4 bg-black/20 rounded-xl border border-black/10">
                  <span className="text-xs font-bold text-[#F2F0E9] uppercase tracking-wider">
                    Minimum Wage
                  </span>
                  <span className="bg-[#1A1A1A] text-[#F2F0E9] px-3 py-1 rounded-md text-[10px] font-mono uppercase tracking-wider shadow-inner">
                    San Diego County
                  </span>
                </div>
              </motion.div>
            </div>
          </div>
        </div>
      </section>

      {/* MANIFESTO SECTION (The Philosophy) */}
      <section
        ref={manifestoRef}
        className="relative py-40 px-6 bg-[#1A1A1A] text-[#F2F0E9] overflow-hidden rounded-[3rem] mx-4 md:mx-8 shadow-2xl"
      >
        <div
          className="phil-bg absolute inset-0 z-0 opacity-30 bg-cover bg-center mix-blend-overlay"
          style={{
            backgroundImage: `url('https://images.unsplash.com/photo-1542601906990-b4d3fb778b09?q=80&w=3500&auto=format&fit=crop')`,
            transform: "scale(1.2)",
          }}
        />
        <div className="relative z-10 max-w-[1800px] mx-auto grid lg:grid-cols-2 gap-24 items-center">
          <div className="space-y-12">
            <div className="inline-flex items-center gap-2 px-4 py-2 bg-white/5 rounded-full border border-white/10 text-[10px] font-mono uppercase tracking-widest text-[#F2F0E9]/60">
              <Sparkles className="w-3 h-3 text-[#CC5833]" /> Manifesto
            </div>
            <h2
              className="phil-text text-5xl md:text-7xl font-bold tracking-tighter leading-[0.85]"
              style={{ fontFamily: fonts.sans }}
            >
              AI SHOULD FREE US <br />
              <span
                className="text-[#CC5833] italic font-light"
                style={{ fontFamily: fonts.serif }}
              >
                Not Replace Us.
              </span>
            </h2>
            <div className="phil-text space-y-6 text-[#F2F0E9]/70 text-lg md:text-xl font-light leading-relaxed max-w-xl">
              <p>
                The promise of automation was never about removing the human
                element. It was about stripping away the administrative noise
                that keeps people from doing their best work.
              </p>
              <p>
                We build agentic systems that handle the complex, the
                repetitive, and the regulatory — freeing up workers to engage in
                more meaningful, high-leverage activities.
              </p>
            </div>
          </div>
          <div className="relative">
            <div className="absolute inset-0 bg-[#2E4036]/20 blur-[100px] rounded-full" />
            <div className="relative grid grid-cols-2 gap-4">
              {[
                { label: "Admin Burden", value: "-85%", icon: Zap },
                { label: "Strategic Focus", value: "4x", icon: Sparkles },
              ].map((item, i) => (
                <div
                  key={i}
                  className="phil-text bg-white/5 backdrop-blur-sm border border-white/10 rounded-[2rem] p-8 space-y-4"
                >
                  <item.icon className="w-6 h-6 text-[#CC5833]" />
                  <div>
                    <div
                      className="text-4xl font-bold tracking-tighter text-[#F2F0E9]"
                      style={{ fontFamily: fonts.sans }}
                    >
                      {item.value}
                    </div>
                    <div className="text-[10px] font-mono uppercase tracking-widest text-[#F2F0E9]/50 mt-2">
                      {item.label}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* INTERVIEWER SECTION (Neural Stream Ascii style) */}
      <section className="py-32 px-6 bg-[#F2F0E9] relative overflow-hidden">
        <div className="max-w-[1800px] mx-auto grid lg:grid-cols-2 gap-24 items-center relative z-10">
          <div className="order-2 lg:order-1 relative">
            <div className="relative aspect-square max-w-md mx-auto bg-[#1A1A1A] rounded-[3rem] border border-[#2E4036]/20 shadow-2xl flex flex-col items-center justify-center p-12 overflow-hidden group">
              <AsciiWaveform />
              <div className="mt-12 w-full space-y-4 font-mono">
                <div className="flex justify-between text-[10px] text-[#CC5833] uppercase tracking-widest">
                  <span>Voice Protocol</span>
                  <span>Active</span>
                </div>
                <div className="h-1 w-full bg-white/10 rounded-full relative overflow-hidden">
                  <motion.div
                    animate={{ width: ["20%", "80%", "45%", "95%", "30%"] }}
                    transition={{
                      duration: 4,
                      repeat: Infinity,
                      ease: "easeInOut",
                    }}
                    className="absolute inset-y-0 left-0 bg-[#CC5833] rounded-full"
                  />
                </div>
                <div className="text-[9px] text-[#F2F0E9]/50 uppercase tracking-widest flex justify-between">
                  <span className="text-[#CC5833] animate-pulse">● Rec</span>
                  <span>Buffer: 99%</span>
                </div>
              </div>
            </div>
          </div>

          <div className="order-1 lg:order-2 space-y-12">
            <div className="inline-flex items-center gap-2 px-4 py-2 bg-[#2E4036]/10 rounded-full border border-[#2E4036]/20 text-[10px] font-mono uppercase tracking-widest text-[#2E4036]">
              <Zap className="w-3 h-3" /> Agentic Voice
            </div>
            <h2
              className="text-6xl md:text-8xl font-bold tracking-tighter leading-[0.85] text-[#1A1A1A]"
              style={{ fontFamily: fonts.sans }}
            >
              THE <br />
              <span
                className="italic text-[#2E4036] font-light"
                style={{ fontFamily: fonts.serif }}
              >
                Interviewer.
              </span>
            </h2>
            <p className="text-[#1A1A1A]/70 text-xl font-light leading-relaxed max-w-xl">
              Replace standard screening forms with high-fidelity, autonomous
              voice agents that conduct natural conversations and extract deep
              cultural insights.
            </p>

            <div className="grid sm:grid-cols-2 gap-8 pt-8 border-t border-[#1A1A1A]/10">
              {[
                {
                  title: "Latent Analysis",
                  desc: "Detects confidence, sentiment, and hesitation markers through proprietary audio processing.",
                },
                {
                  title: "Dynamic Probing",
                  desc: "Agents listen and ask intelligent follow-up questions based on candidate responses.",
                },
              ].map((item, i) => (
                <div key={i} className="space-y-3">
                  <h4 className="font-bold text-[#1A1A1A] uppercase tracking-wider text-sm">
                    {item.title}
                  </h4>
                  <p className="text-[#1A1A1A]/60 text-sm leading-relaxed">
                    {item.desc}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <Marquee>
        Automation • Compliance • Intelligence • Efficiency • Security • Scale
        •{" "}
      </Marquee>

      {/* SYSTEM PROTOCOL (Sticky Stacking Archive) */}
      <section ref={systemRef} className="relative mt-24">
        {/* Module 1: ER Copilot */}
        <div className="system-card sticky top-0 h-screen w-full flex items-center justify-center p-6 bg-[#2E4036] text-[#F2F0E9] origin-top">
          <div className="max-w-6xl w-full grid grid-cols-1 md:grid-cols-2 gap-16 items-center">
            <div className="space-y-6">
              <div className="text-[10px] uppercase tracking-[0.2em] text-[#CC5833] font-mono">
                Module 01
              </div>
              <h2
                className="text-6xl md:text-8xl italic"
                style={{ fontFamily: fonts.serif }}
              >
                ER Copilot
              </h2>
              <p
                className="text-xl font-light opacity-80"
                style={{ fontFamily: fonts.sans }}
              >
                Your automated legal counsel. Resolves complex employee
                relations cases using your specific policy handbook and local
                law routing.
              </p>
            </div>
            <div className="flex justify-center items-center h-[400px] border border-white/10 rounded-[3rem] bg-black/20 p-12 relative overflow-hidden">
              <Cpu
                size={120}
                className="text-[#CC5833] opacity-80"
                strokeWidth={1}
              />
              <div className="absolute top-8 right-8 text-[10px] font-mono text-white/50 uppercase">
                Bias Detection Active
              </div>
            </div>
          </div>
        </div>

        {/* Module 2: Policy Hub */}
        <div className="system-card sticky top-0 h-screen w-full flex items-center justify-center p-6 bg-[#1A1A1A] text-[#F2F0E9] origin-top shadow-2xl">
          <div className="max-w-6xl w-full grid grid-cols-1 md:grid-cols-2 gap-16 items-center">
            <div className="flex justify-center items-center h-[400px] border border-[#2E4036] rounded-[3rem] bg-[#2E4036]/10 relative overflow-hidden group order-2 md:order-1">
              <FileText size={120} className="text-[#2E4036]" strokeWidth={1} />
              <div className="absolute bottom-8 left-8 right-8 bg-[#1A1A1A] rounded-full h-2 overflow-hidden border border-white/10">
                <div className="bg-[#F2F0E9] h-full w-[100%]" />
              </div>
            </div>
            <div className="space-y-6 order-1 md:order-2">
              <div className="text-[10px] uppercase tracking-[0.2em] text-[#2E4036] font-mono">
                Module 02
              </div>
              <h2
                className="text-6xl md:text-8xl italic"
                style={{ fontFamily: fonts.serif }}
              >
                Policy Hub
              </h2>
              <p
                className="text-xl font-light opacity-80"
                style={{ fontFamily: fonts.sans }}
              >
                A living repository for your organization's laws. Track
                acknowledgements in real-time, deployed dynamically by
                jurisdiction.
              </p>
            </div>
          </div>
        </div>

        {/* Module 3: Incident Reporting */}
        <div className="system-card sticky top-0 h-screen w-full flex items-center justify-center p-6 bg-[#F2F0E9] text-[#1A1A1A] origin-top shadow-[0_-20px_50px_rgba(0,0,0,0.3)]">
          <div className="max-w-6xl w-full grid grid-cols-1 md:grid-cols-2 gap-16 items-center">
            <div className="space-y-6">
              <div className="text-[10px] uppercase tracking-[0.2em] text-[#CC5833] font-mono">
                Module 03
              </div>
              <h2
                className="text-6xl md:text-8xl italic text-[#2E4036]"
                style={{ fontFamily: fonts.serif }}
              >
                Incident Reporting
              </h2>
              <p
                className="text-xl font-light opacity-80"
                style={{ fontFamily: fonts.sans }}
              >
                Structured workflows for safety and security. Audit-ready logs
                generated automatically, synthesizing emails and chat
                transcripts.
              </p>
            </div>
            <div className="flex justify-center items-center h-[400px] border border-[#1A1A1A]/10 rounded-[3rem] bg-white relative shadow-xl">
              <Shield size={120} className="text-[#CC5833]" strokeWidth={1} />
              <button
                onClick={() => setIsContactOpen(true)}
                className="absolute bottom-8 rounded-full bg-[#1A1A1A] text-white px-6 py-3 text-xs font-mono uppercase tracking-widest hover:scale-105 transition-transform"
              >
                Initialize Module
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* FOOTER PREVIEW / STATS */}
      <section className="py-24 border-t border-[#1A1A1A]/10 bg-[#F2F0E9]">
        <div className="max-w-[1800px] mx-auto px-6 grid grid-cols-2 md:grid-cols-4 gap-12">
          {[
            { label: "Uptime", value: "99.99%" },
            { label: "Reliability", value: "High" },
            { label: "Deploy", value: "< 5min" },
            { label: "Support", value: "24/7" },
          ].map((stat, i) => (
            <div key={i} className="border-l border-[#1A1A1A]/20 pl-6">
              <div className="text-[10px] font-mono uppercase tracking-widest text-[#CC5833] mb-2">
                {stat.label}
              </div>
              <div
                className="text-4xl font-light text-[#1A1A1A]"
                style={{ fontFamily: fonts.serif }}
              >
                {stat.value}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* MAIN FOOTER */}
      <footer className="bg-[#1A1A1A] text-[#F2F0E9] py-24 px-6 rounded-t-[4rem] relative z-20 shadow-[0_-20px_60px_rgba(0,0,0,0.5)]">
        <div className="max-w-[1800px] mx-auto">
          <div className="flex flex-col md:flex-row justify-between items-start gap-12">
            <div>
              <h2
                className="text-6xl md:text-8xl font-bold tracking-tighter leading-none mb-8"
                style={{ fontFamily: fonts.sans }}
              >
                READY TO <br />
                <span
                  className="italic text-[#CC5833] font-light"
                  style={{ fontFamily: fonts.serif }}
                >
                  Deploy?
                </span>
              </h2>
              <button
                onClick={() => setIsContactOpen(true)}
                className="inline-block px-8 py-4 bg-[#F2F0E9] text-[#1A1A1A] rounded-full font-mono text-sm uppercase tracking-widest hover:scale-[1.02] transition-transform font-bold"
              >
                Initialize System
              </button>
            </div>

            <div className="grid grid-cols-2 gap-16 text-sm font-mono uppercase tracking-widest text-[#F2F0E9]/70">
              <div className="space-y-4">
                <span className="text-[#2E4036] text-[10px] block mb-2">
                  Navigation
                </span>
                <span
                  onClick={() => scrollTo(systemRef)}
                  className="block hover:text-white cursor-pointer transition-colors"
                >
                  System Modules
                </span>
                <span
                  onClick={() => scrollTo(manifestoRef)}
                  className="block hover:text-white cursor-pointer transition-colors"
                >
                  Manifesto
                </span>
                <span
                  onClick={() => setIsContactOpen(true)}
                  className="block hover:text-white cursor-pointer transition-colors"
                >
                  Pricing
                </span>
              </div>
              <div className="space-y-4">
                <span className="text-[#2E4036] text-[10px] block mb-2">
                  Legal / Connect
                </span>
                <Link
                  to="/terms"
                  className="block hover:text-white transition-colors"
                >
                  Terms of Service
                </Link>
                <a
                  href="#"
                  className="block hover:text-white transition-colors"
                >
                  Twitter
                </a>
                <a
                  href="#"
                  className="block hover:text-white transition-colors"
                >
                  LinkedIn
                </a>
              </div>
            </div>
          </div>

          <div className="mt-24 pt-8 border-t border-white/10 flex justify-between items-center text-[10px] font-mono uppercase tracking-widest text-[#F2F0E9]/40">
            <span>© {new Date().getFullYear()} Matcha Inc.</span>
            <div className="flex items-center gap-3 bg-white/5 px-4 py-2 rounded-full border border-white/5">
              <span className="w-2 h-2 rounded-full bg-[#CC5833] animate-pulse" />
              All Systems Normal
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default Landing;
