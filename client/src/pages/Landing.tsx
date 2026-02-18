import { useRef, lazy, Suspense, useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { motion, useScroll, useTransform, AnimatePresence } from "framer-motion";
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

// Lazy load 3D component
const ParticleSphere = lazy(() => import("../components/ParticleSphere"));

// Marquee Component
const Marquee = ({ children }: { children: React.ReactNode }) => (
  <div className="relative flex overflow-hidden border-y border-white/10 bg-white/5 py-4">
    <div className="animate-marquee whitespace-nowrap flex gap-8">
      {[...Array(4)].map((_, i) => (
        <span
          key={i}
          className="text-4xl font-black uppercase tracking-tighter text-transparent stroke-text opacity-50"
        >
          {children}
        </span>
      ))}
    </div>
    <div className="absolute top-0 flex animate-marquee2 whitespace-nowrap gap-8">
      {[...Array(4)].map((_, i) => (
        <span
          key={i}
          className="text-4xl font-black uppercase tracking-tighter text-transparent stroke-text opacity-50"
        >
          {children}
        </span>
      ))}
    </div>
  </div>
);

const LOCAL_JURISDICTIONS = [
  "San Francisco Local",
  "West Hollywood Local",
  "Los Angeles Local",
  "Berkeley Local",
  "Emeryville Local",
  "Seattle Local",
];

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
          // The parent component handles the text change
        } else {
          timeout = setTimeout(type, 30);
        }
      }
    };

    timeout = setTimeout(type, isDeleting ? 30 : 50);
    return () => clearTimeout(timeout);
  }, [displayText, isDeleting, text]);

  // Reset when text changes from parent
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
        className="w-1 h-3 bg-emerald-400 ml-0.5"
      />
    </span>
  );
};

const TalkingMouth = () => {
  return (
    <div className="font-mono text-emerald-500 leading-none select-none">
      <motion.pre
        animate={{
          opacity: [0.4, 1, 0.4],
          scaleY: [1, 1.4, 0.9, 1.3, 1],
          filter: [
            "drop-shadow(0 0 2px rgba(16,185,129,0.3))",
            "drop-shadow(0 0 8px rgba(16,185,129,0.6))",
            "drop-shadow(0 0 2px rgba(16,185,129,0.3))",
          ],
        }}
        transition={{
          duration: 0.2,
          repeat: Infinity,
          ease: "linear"
        }}
        className="text-[10px] md:text-xs"
      >
{`
         .------------------.
       /  .----------------.  \\
      |  /                  \\  |
      | |                    | |
      | |                    | |
      |  \\                  /  |
       \\  '----------------'  /
         '------------------'
`}
      </motion.pre>
    </div>
  );
};

function ContactModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const [formData, setFormData] = useState({ name: "", email: "", message: "" });
  const [sent, setSent] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // In a real app, you'd send this to a backend. 
    // Here we'll just simulate and open mailto
    const mailtoUrl = `mailto:aaron@hey-matcha.com?subject=Matcha Pricing Inquiry from ${formData.name}&body=${formData.message}%0D%0A%0D%0AFrom: ${formData.email}`;
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
            className="absolute inset-0 bg-black/90 backdrop-blur-md"
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            className="relative w-full max-w-lg bg-zinc-900 border border-white/10 p-8 md:p-12 shadow-2xl"
          >
            <button onClick={onClose} className="absolute top-6 right-6 text-zinc-500 hover:text-white transition-colors">
              <X className="w-6 h-6" />
            </button>

            {sent ? (
              <div className="py-12 text-center space-y-4">
                <div className="w-16 h-16 bg-emerald-500/20 rounded-full flex items-center justify-center mx-auto mb-6">
                  <Send className="w-8 h-8 text-emerald-400" />
                </div>
                <h3 className="text-2xl font-bold uppercase tracking-tighter">Request Received</h3>
                <p className="text-zinc-500 font-mono text-sm uppercase tracking-widest leading-relaxed">
                  Redirecting to mail client...
                </p>
              </div>
            ) : (
              <div className="space-y-8">
                <div>
                  <h3 className="text-3xl font-bold uppercase tracking-tighter mb-2">Request Pricing</h3>
                  <p className="text-zinc-500 font-mono text-[10px] uppercase tracking-[0.2em]">Contact: aaron@hey-matcha.com</p>
                </div>

                <form onSubmit={handleSubmit} className="space-y-6">
                  <div className="space-y-2">
                    <label className="text-[10px] font-mono uppercase tracking-widest text-zinc-500 ml-1">Full Name</label>
                    <input
                      required
                      type="text"
                      value={formData.name}
                      onChange={e => setFormData({ ...formData, name: e.target.value })}
                      className="w-full bg-black border border-white/10 px-4 py-3 text-sm focus:border-white/30 outline-none transition-colors"
                      placeholder="Jane Doe"
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-[10px] font-mono uppercase tracking-widest text-zinc-500 ml-1">Work Email</label>
                    <input
                      required
                      type="email"
                      value={formData.email}
                      onChange={e => setFormData({ ...formData, email: e.target.value })}
                      className="w-full bg-black border border-white/10 px-4 py-3 text-sm focus:border-white/30 outline-none transition-colors"
                      placeholder="jane@company.com"
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-[10px] font-mono uppercase tracking-widest text-zinc-500 ml-1">Project Requirements</label>
                    <textarea
                      required
                      rows={4}
                      value={formData.message}
                      onChange={e => setFormData({ ...formData, message: e.target.value })}
                      className="w-full bg-black border border-white/10 px-4 py-3 text-sm focus:border-white/30 outline-none transition-colors resize-none"
                      placeholder="Tell us about your organization size and which modules you need."
                    />
                  </div>
                  <button
                    type="submit"
                    className="w-full bg-white text-black py-4 font-mono text-sm uppercase tracking-[0.2em] font-bold hover:bg-zinc-200 transition-colors"
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

export function Landing() {
  const containerRef = useRef<HTMLDivElement>(null);
  const complianceSectionRef = useRef<HTMLDivElement>(null);
  const manifestoRef = useRef<HTMLDivElement>(null);
  const systemRef = useRef<HTMLDivElement>(null);
  
  const [jurisdictionIndex, setJurisdictionIndex] = useState(0);
  const [isContactOpen, setIsContactOpen] = useState(false);

  useEffect(() => {
    const timer = setInterval(() => {
      setJurisdictionIndex((prev) => (prev + 1) % LOCAL_JURISDICTIONS.length);
    }, 5000);
    return () => clearInterval(timer);
  }, []);

  const { scrollYProgress } = useScroll({
    target: complianceSectionRef,
    offset: ["start end", "end start"],
  });

  const card1Y = useTransform(scrollYProgress, [0, 1], [100, -100]);
  const card2Y = useTransform(scrollYProgress, [0, 1], [150, -150]);

  const scrollTo = (ref: React.RefObject<HTMLDivElement>) => {
    ref.current?.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <div
      ref={containerRef}
      className="bg-zinc-950 text-zinc-100 font-sans selection:bg-white selection:text-black overflow-x-hidden"
    >
      <ContactModal isOpen={isContactOpen} onClose={() => setIsContactOpen(false)} />
      {/* Noise Overlay */}
      <div className="fixed inset-0 pointer-events-none z-50 bg-noise opacity-50 mix-blend-overlay" />

      {/* Navigation */}
      <nav className="fixed top-0 inset-x-0 z-40 border-b border-white/5 bg-zinc-950/80 backdrop-blur-xl">
        <div className="flex items-center justify-between px-6 h-16 max-w-[1800px] mx-auto">
          <Link to="/" className="flex items-center gap-3 group">
            <div className="w-8 h-8 bg-white flex items-center justify-center">
              <div className="w-3 h-3 bg-black group-hover:scale-0 transition-transform duration-500" />
            </div>
            <span className="font-mono text-sm tracking-widest uppercase">
              Matcha
            </span>
          </Link>
          <div className="flex items-center gap-8">
            <div className="hidden md:flex gap-6 text-xs font-mono uppercase tracking-widest text-zinc-500">
              <span onClick={() => scrollTo(manifestoRef)} className="hover:text-white cursor-pointer transition-colors">
                Manifesto
              </span>
              <span onClick={() => scrollTo(systemRef)} className="hover:text-white cursor-pointer transition-colors">
                System
              </span>
              <span onClick={() => setIsContactOpen(true)} className="hover:text-white cursor-pointer transition-colors">
                Pricing
              </span>
            </div>
            <Link
              to="/login"
              className="px-6 py-2 border border-white/20 text-xs font-mono uppercase tracking-widest hover:bg-white hover:text-black transition-colors"
            >
              Login
            </Link>
          </div>
        </div>
      </nav>

      {/* HERO SECTION */}
      <section className="relative min-h-screen flex flex-col justify-center px-6 pt-20 border-b border-white/5">
        <div className="max-w-[1800px] mx-auto w-full grid lg:grid-cols-2 gap-12 items-center">
          <div className="relative z-20 space-y-12">
            <div>
              <motion.div
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                className="inline-flex items-center gap-3 px-4 py-2 border border-white/10 rounded-full mb-8 bg-white/5"
              >
                <span className="w-2 h-2 bg-emerald-500 animate-pulse" />
                <span className="text-[10px] font-mono uppercase tracking-widest text-zinc-400">
                  System v2.4 Live
                </span>
              </motion.div>

              <h1 className="text-7xl md:text-9xl font-bold tracking-tighter leading-[0.85] mix-blend-difference">
                COMPANY <br />
                <span className="text-zinc-500">SUCCESS</span> <br />
                ENGINE
              </h1>
            </div>

            <div className="flex flex-col md:flex-row gap-8 items-start md:items-center max-w-xl">
              <p className="text-zinc-400 text-lg leading-relaxed font-light">
                The operating system for modern workforce management. <br />
                Stripped of noise. Powered by intelligence.
              </p>
              <Link
                to="/register"
                className="group flex items-center gap-4 border-b border-white pb-1 hover:pb-2 transition-all"
              >
                <span className="text-sm font-mono uppercase tracking-widest">
                  Get Started
                </span>
                <ArrowUpRight className="w-4 h-4 group-hover:-translate-y-1 group-hover:translate-x-1 transition-transform" />
              </Link>
            </div>
          </div>

          <div className="relative h-[60vh] lg:h-[80vh] w-full flex items-center justify-center z-0">
            <Suspense
              fallback={
                <div className="w-full h-full flex items-center justify-center text-zinc-800">
                  Loading 3D...
                </div>
              }
            >
              <ParticleSphere className="w-full h-full scale-125 lg:scale-150" />
            </Suspense>

            {/* Floating UI Elements */}
            <motion.div
              initial={{ opacity: 0, y: 50 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.5 }}
              className="absolute bottom-10 -left-10 md:left-0 bg-black/80 backdrop-blur border border-white/10 p-6 max-w-xs"
            >
              <div className="flex items-center gap-3 mb-4 text-xs font-mono text-zinc-500 uppercase tracking-widest border-b border-white/10 pb-2">
                <Terminal className="w-3 h-3" />
                <span>System Output</span>
              </div>
              <div className="space-y-2 font-mono text-[10px] text-emerald-500">
                <div>&gt; Analyzing policy constraints...</div>
                <div>&gt; 142 Documents Processed</div>
                <div>&gt; Compliance Verified (99.9%)</div>
              </div>
            </motion.div>
          </div>
        </div>
      </section>

      {/* COMPLIANCE SECTION */}
      <section
        ref={complianceSectionRef}
        className="py-32 px-6 border-b border-white/5 bg-zinc-950 relative overflow-hidden"
      >
        {/* Texture Overlay */}
        <div className="absolute inset-0 bg-noise opacity-[0.15] mix-blend-soft-light pointer-events-none" />
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-zinc-950/50 to-zinc-950 pointer-events-none" />

        <div className="max-w-[1800px] mx-auto grid lg:grid-cols-2 gap-24 items-center relative z-10">
          <div className="space-y-12">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.8 }}
            >
              <h2 className="text-5xl md:text-7xl font-bold tracking-tighter leading-[0.9] mb-8">
                KNOW EXACTLY <br />
                WHICH LAW APPLIES <br />
                <span className="text-zinc-500">— AT EVERY LOCATION</span>
              </h2>
              <p className="text-zinc-400 text-xl leading-relaxed max-w-xl font-light">
                Matcha monitors labor laws across city, county, and state levels
                — and tells you which one governs each requirement at each
                location.
              </p>
            </motion.div>

            <div className="space-y-8">
              {[
                {
                  title: "Knows when cities defer to county or state",
                  desc: "Del Mar doesn't have its own minimum wage. Matcha knows that and shows you San Diego County's rules, not a hallucinated city ordinance.",
                },
                {
                  title: "Picks the rule that actually applies",
                  desc: "When state and city both set a minimum wage, Matcha applies the one that's most beneficial to the employee.",
                },
                {
                  title: "Monitors for changes across every level",
                  desc: "New state law? County ordinance update? Upcoming legislation? You get alerts with sources and confidence scores.",
                },
              ].map((point, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: -20 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.5, delay: 0.4 + i * 0.1 }}
                  className="flex gap-6"
                >
                  <div className="text-zinc-600 font-mono text-sm mt-1">
                    0{i + 1}
                  </div>
                  <div className="space-y-2">
                    <h4 className="font-bold text-white uppercase tracking-tight">
                      {point.title}
                    </h4>
                    <p className="text-sm text-zinc-500 leading-relaxed max-w-md">
                      {point.desc}
                    </p>
                  </div>
                </motion.div>
              ))}
            </div>
          </div>

          <div className="relative perspective-[1000px]">
            {/* Mock UI */}
            <div className="space-y-6 relative z-10">
              {/* San Francisco Card */}
              <motion.div
                style={{ y: card1Y }}
                initial={{ opacity: 0, rotateX: 10, rotateY: -5 }}
                whileInView={{ 
                  opacity: 1, 
                  rotateX: [10, 0, 10],
                  rotateY: [-5, 5, -5]
                }}
                viewport={{ once: true }}
                transition={{ 
                  duration: 12, 
                  repeat: Infinity, 
                  ease: "easeInOut",
                  opacity: { duration: 0.8, repeat: 0 }
                }}
                className="bg-zinc-900 border border-white/10 p-6 shadow-2xl relative z-20 overflow-hidden group"
              >
                {/* Continuous Shimmer */}
                <motion.div 
                  animate={{ x: ["-100%", "200%"] }}
                  transition={{ duration: 4, repeat: Infinity, ease: "linear", delay: 1 }}
                  className="absolute inset-0 bg-gradient-to-r from-transparent via-white/5 to-transparent pointer-events-none" 
                />
                
                {/* Continuous Scan Line */}
                <motion.div 
                  animate={{ top: ["-10%", "110%"] }}
                  transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
                  className="absolute left-0 right-0 h-px bg-emerald-500/50 shadow-[0_0_15px_rgba(16,185,129,0.8)] z-30" 
                />

                <div className="relative z-10">
                  <div className="flex items-center justify-between mb-6 pb-4 border-b border-white/5">
                    <div className="flex items-center gap-3">
                      <MapPin className="w-4 h-4 text-zinc-500" />
                      <span className="text-xs font-mono uppercase tracking-widest text-zinc-300">
                        Global Coverage
                      </span>
                    </div>
                    <div className="px-2 py-0.5 bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 text-[10px] font-mono uppercase flex items-center gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                      Active
                    </div>
                  </div>

                  <div className="space-y-px bg-white/5 border border-white/5">
                    {[
                      {
                        label: "Minimum Wage",
                        badge: LOCAL_JURISDICTIONS[jurisdictionIndex],
                        color: "emerald",
                        isDynamic: true,
                      },
                      {
                        label: "Sick Leave",
                        badge: "California",
                        color: "blue",
                      },
                      { label: "Overtime", badge: "California", color: "blue" },
                      {
                        label: "Meal Breaks",
                        badge: "California",
                        color: "blue",
                      },
                    ].map((row, i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between p-4 bg-zinc-950 min-h-[52px]"
                      >
                        <span className="text-xs font-bold text-zinc-300 uppercase tracking-wider">
                          {row.label}
                        </span>
                        <div className="relative flex justify-end min-w-[160px]">
                          <span
                            className={`px-2 py-0.5 rounded border text-[10px] font-bold uppercase tracking-wider whitespace-nowrap flex items-center min-h-[22px] ${
                              row.color === "emerald"
                                ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                                : "bg-blue-500/15 text-blue-400 border-blue-500/30"
                            }`}
                          >
                            {row.isDynamic ? (
                              <TypewriterBadge text={row.badge} />
                            ) : (
                              row.badge
                            )}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </motion.div>

              {/* Del Mar Card */}
              <motion.div
                style={{ y: card2Y }}
                initial={{ opacity: 0, rotateX: 5, rotateY: 5 }}
                whileInView={{ 
                  opacity: 0.8, 
                  rotateX: [5, -5, 5],
                  rotateY: [5, -5, 5]
                }}
                viewport={{ once: true }}
                transition={{ 
                  duration: 10, 
                  repeat: Infinity, 
                  ease: "easeInOut",
                  opacity: { duration: 0.8, delay: 0.2, repeat: 0 }
                }}
                className="bg-zinc-900 border border-white/10 p-6 shadow-2xl scale-95 origin-right relative overflow-hidden"
              >
                {/* Continuous Shimmer */}
                <motion.div 
                  animate={{ x: ["-100%", "200%"] }}
                  transition={{ duration: 5, repeat: Infinity, ease: "linear" }}
                  className="absolute inset-0 bg-gradient-to-r from-transparent via-white/5 to-transparent pointer-events-none" 
                />

                <div className="relative z-10">
                  <div className="flex items-center justify-between mb-6 pb-4 border-b border-white/5">
                    <div className="flex items-center gap-3">
                      <MapPin className="w-4 h-4 text-zinc-500" />
                      <span className="text-xs font-mono uppercase tracking-widest text-zinc-300">
                        Del Mar, CA
                      </span>
                    </div>
                  </div>
                  <div className="space-y-px bg-white/5 border border-white/5">
                    <div className="flex items-center justify-between p-4 bg-zinc-950">
                      <span className="text-xs font-bold text-zinc-300 uppercase tracking-wider">
                        Minimum Wage
                      </span>
                      <span className="bg-blue-500/15 text-blue-400 border-blue-500/30 px-2 py-0.5 rounded border text-[10px] font-bold uppercase tracking-wider">
                        San Diego County
                      </span>
                    </div>
                  </div>
                </div>
              </motion.div>
            </div>

            {/* Background elements */}
            <motion.div
              animate={{
                scale: [1, 1.2, 1],
                opacity: [0.05, 0.1, 0.05],
              }}
              transition={{
                duration: 8,
                repeat: Infinity,
                ease: "easeInOut",
              }}
              className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[120%] h-[120%] bg-white/5 blur-3xl rounded-full -z-10"
            />
          </div>
        </div>
      </section>

      {/* MANIFESTO SECTION */}
      <section ref={manifestoRef} className="py-32 px-6 border-b border-white/5 relative overflow-hidden">
        <div className="max-w-[1800px] mx-auto grid lg:grid-cols-2 gap-24 items-center">
          <div className="space-y-12">
            <div className="inline-flex items-center gap-2 px-3 py-1 bg-white/5 border border-white/10 text-[10px] font-mono uppercase tracking-widest text-zinc-500">
              <Sparkles className="w-3 h-3 text-emerald-400" />
              Manifesto
            </div>
            <h2 className="text-6xl md:text-8xl font-bold tracking-tighter leading-[0.85]">
              AI SHOULD FREE US <br />
              <span className="text-zinc-500">NOT REPLACE US</span>
            </h2>
            <div className="space-y-6 text-zinc-400 text-lg md:text-xl font-light leading-relaxed max-w-xl">
              <p>
                The promise of automation was never about removing the human element. It was about stripping away the administrative noise that keeps people from doing their best work.
              </p>
              <p>
                We build agentic systems that handle the complex, the repetitive, and the regulatory — freeing up workers to engage in more meaningful, high-leverage activities that drive organizational growth.
              </p>
            </div>
          </div>
          <div className="relative">
            <div className="absolute inset-0 bg-emerald-500/10 blur-[120px] rounded-full" />
            <div className="relative grid grid-cols-2 gap-4">
              {[
                { label: "Administrative Burden", value: "-85%", icon: Zap },
                { label: "Strategic Focus", value: "4x", icon: Sparkles },
              ].map((item, i) => (
                <div key={i} className="bg-zinc-900/50 border border-white/10 p-8 space-y-4">
                  <item.icon className="w-6 h-6 text-emerald-400" />
                  <div>
                    <div className="text-4xl font-bold tracking-tighter">{item.value}</div>
                    <div className="text-[10px] font-mono uppercase tracking-widest text-zinc-500 mt-1">{item.label}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* SYSTEM SECTION */}
      <section ref={systemRef} className="py-32 px-6 border-b border-white/5 bg-white text-black relative">
        <div className="max-w-[1800px] mx-auto">
          <div className="grid lg:grid-cols-12 gap-12 items-start">
            <div className="lg:col-span-4 space-y-8">
              <div className="inline-flex items-center gap-2 px-3 py-1 bg-black/5 border border-black/10 text-[10px] font-mono uppercase tracking-widest text-zinc-500">
                <Cpu className="w-3 h-3 text-black" />
                The Engine
              </div>
              <h2 className="text-5xl md:text-7xl font-bold tracking-tighter leading-[0.9]">
                PROPRIETARY <br /> AGENTIC <br /> SYSTEMS
              </h2>
              <p className="text-zinc-600 text-lg font-light leading-relaxed">
                Matcha runs on a custom layer of autonomous agents designed specifically for the complexities of labor compliance and employee relations.
              </p>
            </div>
            <div className="lg:col-span-8 grid md:grid-cols-2 gap-px bg-black/10 border border-black/10">
              {[
                {
                  title: "Autonomous Research",
                  desc: "Agents continuously crawl municipal, county, and state databases to detect shifts in labor law before they're officially codified.",
                },
                {
                  title: "Policy Reasoning",
                  desc: "Neural inference engines map complex legal requirements directly to your unique organizational constraints in real-time.",
                },
                {
                  title: "Predictive Compliance",
                  desc: "Identify potential regulatory breaches before they occur through deep-pattern analysis of workforce data.",
                },
                {
                  title: "Case Synthesis",
                  desc: "AI agents synthesize interview transcripts, emails, and logs into structured evidence trails for instant ER resolution.",
                },
              ].map((feat, i) => (
                <div key={i} className="bg-white p-12 space-y-4">
                  <div className="text-[10px] font-mono text-zinc-400">0{i+1}</div>
                  <h4 className="text-xl font-bold uppercase tracking-tight">{feat.title}</h4>
                  <p className="text-sm text-zinc-500 leading-relaxed">{feat.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* MARQUEE */}
      <div className="py-20 border-b border-white/5 overflow-hidden">
        <Marquee>
          AUTOMATION COMPLIANCE INTELLIGENCE EFFICIENCY SECURITY SCALE
        </Marquee>
      </div>

      {/* INTERVIEWER SECTION */}
      <section className="py-32 px-6 border-b border-white/5 bg-black relative overflow-hidden">
        {/* Animated Background Grid */}
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#1f1f1f_1px,transparent_1px),linear-gradient(to_bottom,#1f1f1f_1px,transparent_1px)] bg-[size:4rem_4px] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_0%,#000_70%,transparent_100%)] opacity-20" />
        
        <div className="max-w-[1800px] mx-auto grid lg:grid-cols-2 gap-24 items-center relative z-10">
          <div className="order-2 lg:order-1 relative">
            {/* Scanner Effect */}
            <div className="absolute -inset-10 bg-emerald-500/5 blur-[100px] rounded-full animate-pulse" />
            
            <div className="relative aspect-square max-w-md mx-auto border border-white/10 bg-zinc-950/50 flex flex-col items-center justify-center p-12 overflow-hidden group">
              {/* Corner Accents */}
              <div className="absolute top-0 left-0 w-4 h-4 border-t-2 border-l-2 border-emerald-500/40" />
              <div className="absolute top-0 right-0 w-4 h-4 border-t-2 border-r-2 border-emerald-500/40" />
              <div className="absolute bottom-0 left-0 w-4 h-4 border-b-2 border-l-2 border-emerald-500/40" />
              <div className="absolute bottom-0 right-0 w-4 h-4 border-b-2 border-r-2 border-emerald-500/40" />
              
              <TalkingMouth />
              
              <div className="mt-12 w-full space-y-4 font-mono">
                <div className="flex justify-between text-[10px] text-emerald-500/60 uppercase tracking-widest">
                  <span>Voice Signal</span>
                  <span>Active</span>
                </div>
                <div className="h-1 w-full bg-white/5 relative">
                  <motion.div 
                    animate={{ width: ["20%", "80%", "45%", "95%", "30%"] }}
                    transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
                    className="absolute inset-y-0 left-0 bg-emerald-500/40 shadow-[0_0_10px_rgba(16,185,129,0.5)]" 
                  />
                </div>
                <div className="text-[9px] text-zinc-600 uppercase tracking-widest flex gap-4">
                  <span className="animate-pulse">● Rec</span>
                  <span>00:04:12</span>
                  <span className="text-zinc-800">Buffer: 99%</span>
                </div>
              </div>

              {/* HUD Text */}
              <div className="absolute top-6 left-6 text-[8px] font-mono text-zinc-700 uppercase tracking-[0.3em] vertical-text">
                Neural Interface v4.0
              </div>
            </div>
          </div>

          <div className="order-1 lg:order-2 space-y-12">
            <div className="inline-flex items-center gap-2 px-3 py-1 bg-emerald-500/5 border border-emerald-500/10 text-[10px] font-mono uppercase tracking-widest text-emerald-500">
              <Zap className="w-3 h-3" />
              Agentic Voice
            </div>
            
            <h2 className="text-6xl md:text-8xl font-bold tracking-tighter leading-[0.85]">
              THE <br />
              <span className="text-emerald-500">INTERVIEWER</span>
            </h2>
            
            <p className="text-zinc-400 text-xl font-light leading-relaxed max-w-xl">
              Replace standard screening forms with high-fidelity, autonomous voice agents that conduct natural conversations and extract deep cultural insights.
            </p>

            <div className="grid sm:grid-cols-2 gap-8 pt-8 border-t border-white/5">
              {[
                { 
                  title: "Latent Analysis", 
                  desc: "Detects confidence, sentiment, and hesitation markers through proprietary audio processing."
                },
                { 
                  title: "Dynamic Probing", 
                  desc: "Agents listen and ask intelligent follow-up questions based on candidate responses."
                }
              ].map((item, i) => (
                <div key={i} className="space-y-3">
                  <h4 className="font-bold text-white uppercase tracking-wider text-sm">{item.title}</h4>
                  <p className="text-zinc-500 text-sm leading-relaxed">{item.desc}</p>
                </div>
              ))}
            </div>

            <Link
              to="/register"
              className="inline-flex items-center gap-4 bg-emerald-500 text-black px-8 py-4 font-mono text-sm uppercase tracking-widest font-bold hover:bg-emerald-400 transition-colors mt-4"
            >
              Deploy Agent
              <ArrowUpRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </section>

      {/* FEATURE GRID */}
      <section className="py-32 px-6 max-w-[1800px] mx-auto">
        <div className="mb-24 flex flex-col md:flex-row justify-between items-end gap-8">
          <h2 className="text-5xl md:text-7xl font-bold tracking-tighter max-w-2xl">
            CORE <br /> ARCHITECTURE
          </h2>
          <div className="text-right">
            <div className="text-xs font-mono uppercase tracking-widest text-zinc-500 mb-2">
              Available Modules
            </div>
            <div className="text-4xl font-light text-zinc-300">04</div>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-12 gap-px bg-white/10 border border-white/10">
          {/* LARGE CARD: ER COPILOT */}
          <div className="lg:col-span-8 bg-zinc-950 p-12 md:p-20 relative group overflow-hidden">
            <div className="absolute inset-0 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-20 group-hover:opacity-40 transition-opacity" />
            <div className="relative z-10">
              <Cpu className="w-12 h-12 text-white mb-8" strokeWidth={1} />
              <h3 className="text-4xl font-bold mb-6">ER Copilot</h3>
              <p className="text-xl text-zinc-400 max-w-md leading-relaxed mb-12">
                Your automated legal counsel. Resolves complex employee
                relations cases using your specific policy handbook.
              </p>
              <div className="grid grid-cols-2 gap-8 font-mono text-xs uppercase tracking-widest text-zinc-500">
                <div className="flex items-center gap-2">
                  <span className="w-1 h-1 bg-emerald-500" />
                  Bias Detection
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-1 h-1 bg-emerald-500" />
                  Policy Citations
                </div>
              </div>
            </div>
            <ArrowUpRight className="absolute top-8 right-8 w-8 h-8 text-white/20 group-hover:text-white group-hover:rotate-45 transition-all" />
          </div>

          {/* TALL CARD: POLICIES */}
          <div className="lg:col-span-4 bg-zinc-950 p-12 md:p-16 relative group border-l border-white/10">
            <div className="h-full flex flex-col justify-between">
              <div>
                <FileText
                  className="w-10 h-10 text-white mb-8"
                  strokeWidth={1}
                />
                <h3 className="text-3xl font-bold mb-4">Policy Hub</h3>
                <p className="text-zinc-400 leading-relaxed">
                  A living repository for your organization's laws. Track
                  acknowledgement in real-time.
                </p>
              </div>
              <div className="mt-12 pt-12 border-t border-white/10">
                <div className="flex justify-between items-center text-xs font-mono uppercase tracking-widest">
                  <span>Coverage</span>
                  <span>100%</span>
                </div>
                <div className="w-full bg-zinc-900 h-1 mt-4">
                  <div className="bg-white h-full w-full" />
                </div>
              </div>
            </div>
          </div>

          {/* CARD: IR */}
          <div className="lg:col-span-4 bg-zinc-950 p-12 relative group border-t border-white/10">
            <Shield className="w-10 h-10 text-white mb-8" strokeWidth={1} />
            <h3 className="text-2xl font-bold mb-4">Incident Reporting</h3>
            <p className="text-sm text-zinc-400 leading-relaxed mb-8">
              Structured workflows for safety and security. Audit-ready logs
              generated automatically.
            </p>
            <Link
              to="/register"
              className="inline-block border-b border-white/20 pb-1 text-xs font-mono uppercase tracking-widest hover:border-white transition-colors"
            >
              Explore Module
            </Link>
          </div>

          {/* CARD: EMPLOYEES */}
          <div className="lg:col-span-4 bg-zinc-950 p-12 relative group border-t border-l border-white/10">
            <Users className="w-10 h-10 text-white mb-8" strokeWidth={1} />
            <h3 className="text-2xl font-bold mb-4">Directory</h3>
            <p className="text-sm text-zinc-400 leading-relaxed mb-8">
              The single source of truth. Roles, departments, and history in one
              view.
            </p>
            <Link
              to="/register"
              className="inline-block border-b border-white/20 pb-1 text-xs font-mono uppercase tracking-widest hover:border-white transition-colors"
            >
              View Data Structure
            </Link>
          </div>

          {/* CARD: OFFERS */}
          <div className="lg:col-span-4 bg-white text-black p-12 relative group border-t border-l border-white/10 hover:bg-zinc-200 transition-colors">
            <div className="absolute top-6 right-6 px-2 py-1 bg-black text-white text-[10px] font-mono uppercase tracking-widest">
              New
            </div>
            <h3 className="text-2xl font-bold mb-4 mt-8">Smart Contracts</h3>
            <p className="text-sm text-black/70 leading-relaxed mb-8">
              Generate error-free offer letters. E-signature ready.
            </p>
            <ArrowUpRight className="w-6 h-6" />
          </div>
        </div>
      </section>

      {/* STATS / FOOTER PREVIEW */}
      <section className="py-32 border-t border-white/5">
        <div className="max-w-[1800px] mx-auto px-6 grid grid-cols-2 md:grid-cols-4 gap-12">
          {[
            { label: "Uptime", value: "99.99%" },
            { label: "Reliability", value: "High" },
            { label: "Deploy", value: "< 5min" },
            { label: "Support", value: "24/7" },
          ].map((stat, i) => (
            <div key={i} className="border-l border-white/20 pl-6">
              <div className="text-xs font-mono uppercase tracking-widest text-zinc-500 mb-2">
                {stat.label}
              </div>
              <div className="text-4xl font-light">{stat.value}</div>
            </div>
          ))}
        </div>
      </section>

      <footer className="bg-white text-black py-24 px-6">
        <div className="max-w-[1800px] mx-auto">
          <div className="flex flex-col md:flex-row justify-between items-start gap-12">
            <div>
              <h2 className="text-6xl md:text-8xl font-bold tracking-tighter leading-none mb-8">
                READY TO <br /> DEPLOY?
              </h2>
              <Link
                to="/register"
                className="inline-block px-8 py-4 bg-black text-white font-mono uppercase tracking-widest hover:bg-zinc-800 transition-colors"
              >
                Initialize System
              </Link>
            </div>

            <div className="grid grid-cols-2 gap-12 text-sm font-mono uppercase tracking-widest">
              <div className="space-y-4">
                <span onClick={() => scrollTo(systemRef)} className="block hover:underline cursor-pointer">
                  System
                </span>
                <span onClick={() => scrollTo(manifestoRef)} className="block hover:underline cursor-pointer">
                  Manifesto
                </span>
                <span onClick={() => setIsContactOpen(true)} className="block hover:underline cursor-pointer">
                  Pricing
                </span>
              </div>
              <div className="space-y-4">
                <a href="#" className="block hover:underline">
                  Twitter
                </a>
                <a href="#" className="block hover:underline">
                  LinkedIn
                </a>
                <a href="#" className="block hover:underline">
                  GitHub
                </a>
              </div>
            </div>
          </div>

          <div className="mt-24 pt-8 border-t border-black/10 flex justify-between items-center text-xs font-mono uppercase tracking-widest opacity-50">
            <span>© 2024 Matcha Inc.</span>
            <span>All Systems Normal</span>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default Landing;

