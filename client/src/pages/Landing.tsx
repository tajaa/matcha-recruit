import { useRef, lazy, Suspense } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowUpRight,
  Terminal,
  Shield,
  FileText,
  Users,
  Cpu,
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

export function Landing() {
  const containerRef = useRef<HTMLDivElement>(null);

  return (
    <div
      ref={containerRef}
      className="bg-zinc-950 text-zinc-100 font-sans selection:bg-white selection:text-black overflow-x-hidden"
    >
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
              <span className="hover:text-white cursor-pointer transition-colors">
                Manifesto
              </span>
              <span className="hover:text-white cursor-pointer transition-colors">
                System
              </span>
              <span className="hover:text-white cursor-pointer transition-colors">
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
                  Start Trial
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

      {/* MARQUEE */}
      <div className="py-20 border-b border-white/5 overflow-hidden">
        <Marquee>
          AUTOMATION COMPLIANCE INTELLIGENCE EFFICIENCY SECURITY SCALE
        </Marquee>
      </div>

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
            { label: "Security", value: "SOC2" },
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
                <a href="#" className="block hover:underline">
                  Product
                </a>
                <a href="#" className="block hover:underline">
                  Manifesto
                </a>
                <a href="#" className="block hover:underline">
                  Pricing
                </a>
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

