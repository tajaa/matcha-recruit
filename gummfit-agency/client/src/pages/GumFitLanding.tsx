import { useRef, lazy, Suspense } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowUpRight,
  Zap,
  DollarSign,
  BarChart3,
  Handshake,
  TrendingUp,
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

export function GumFitLanding() {
  const containerRef = useRef<HTMLDivElement>(null);

  return (
    <div
      ref={containerRef}
      className="bg-zinc-950 text-zinc-100 font-sans selection:bg-emerald-500 selection:text-black overflow-x-hidden"
    >
      {/* Noise Overlay */}
      <div className="fixed inset-0 pointer-events-none z-50 bg-noise opacity-50 mix-blend-overlay" />

      {/* Navigation */}
      <nav className="fixed top-0 inset-x-0 z-40 border-b border-white/5 bg-zinc-950/80 backdrop-blur-xl">
        <div className="flex items-center justify-between px-6 h-16 max-w-[1800px] mx-auto">
          <Link to="/gumfit-landing" className="flex items-center gap-3 group">
            <div className="w-8 h-8 bg-emerald-500 flex items-center justify-center">
              <div className="w-3 h-3 bg-black group-hover:scale-0 transition-transform duration-500" />
            </div>
            <span className="font-mono text-sm tracking-widest uppercase">
              GumFit
            </span>
          </Link>
          <div className="flex items-center gap-8">
            <div className="hidden md:flex gap-6 text-xs font-mono uppercase tracking-widest text-zinc-500">
              <a href="#features" className="hover:text-white cursor-pointer transition-colors">
                Features
              </a>
              <a href="#creators" className="hover:text-white cursor-pointer transition-colors">
                For Creators
              </a>
              <a href="#brands" className="hover:text-white cursor-pointer transition-colors">
                For Brands
              </a>
            </div>
            <Link
              to="/login"
              className="px-6 py-2 border border-emerald-500/50 text-xs font-mono uppercase tracking-widest hover:bg-emerald-500 hover:text-black transition-colors"
            >
              Get Started
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
                className="inline-flex items-center gap-3 px-4 py-2 border border-emerald-500/30 rounded-full mb-8 bg-emerald-500/10"
              >
                <span className="w-2 h-2 bg-emerald-500 animate-pulse" />
                <span className="text-[10px] font-mono uppercase tracking-widest text-emerald-400">
                  Creator Platform Live
                </span>
              </motion.div>

              <h1 className="text-7xl md:text-9xl font-bold tracking-tighter leading-[0.85] mix-blend-difference">
                YOUR <br />
                <span className="text-emerald-500">CREATOR</span> <br />
                EMPIRE
              </h1>
            </div>

            <div className="flex flex-col md:flex-row gap-8 items-start md:items-center max-w-xl">
              <p className="text-zinc-400 text-lg leading-relaxed font-light">
                The operating system for modern creators. <br />
                Connect with brands. Close deals. Get paid.
              </p>
              <Link
                to="/register"
                className="group flex items-center gap-4 border-b border-emerald-500 pb-1 hover:pb-2 transition-all text-emerald-500"
              >
                <span className="text-sm font-mono uppercase tracking-widest">
                  Join Now
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
              className="absolute bottom-10 -left-10 md:left-0 bg-black/80 backdrop-blur border border-emerald-500/20 p-6 max-w-xs"
            >
              <div className="flex items-center gap-3 mb-4 text-xs font-mono text-emerald-500 uppercase tracking-widest border-b border-white/10 pb-2">
                <TrendingUp className="w-3 h-3" />
                <span>Live Metrics</span>
              </div>
              <div className="space-y-2 font-mono text-[10px] text-emerald-500">
                <div>&gt; New brand deal: $12,500</div>
                <div>&gt; Affiliate revenue: +$3,240</div>
                <div>&gt; 47 brands viewing your profile</div>
              </div>
            </motion.div>
          </div>
        </div>
      </section>

      {/* MARQUEE */}
      <div className="py-20 border-b border-white/5 overflow-hidden">
        <Marquee>
          CREATORS BRANDS DEALS REVENUE ANALYTICS GROWTH PARTNERSHIPS
        </Marquee>
      </div>

      {/* FEATURE GRID */}
      <section id="features" className="py-32 px-6 max-w-[1800px] mx-auto">
        <div className="mb-24 flex flex-col md:flex-row justify-between items-end gap-8">
          <h2 className="text-5xl md:text-7xl font-bold tracking-tighter max-w-2xl">
            BUILT FOR <br /> CREATORS
          </h2>
          <div className="text-right">
            <div className="text-xs font-mono uppercase tracking-widest text-zinc-500 mb-2">
              Platform Features
            </div>
            <div className="text-4xl font-light text-zinc-300">04</div>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-12 gap-px bg-white/10 border border-white/10">
          {/* LARGE CARD: DEAL MARKETPLACE */}
          <div className="lg:col-span-8 bg-zinc-950 p-12 md:p-20 relative group overflow-hidden">
            <div className="absolute inset-0 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-20 group-hover:opacity-40 transition-opacity" />
            <div className="relative z-10">
              <Handshake className="w-12 h-12 text-emerald-500 mb-8" strokeWidth={1} />
              <h3 className="text-4xl font-bold mb-6">Deal Marketplace</h3>
              <p className="text-xl text-zinc-400 max-w-md leading-relaxed mb-12">
                Browse brand campaigns, apply to deals, and negotiate terms.
                First to accept wins - like a limit order for sponsorships.
              </p>
              <div className="grid grid-cols-2 gap-8 font-mono text-xs uppercase tracking-widest text-zinc-500">
                <div className="flex items-center gap-2">
                  <span className="w-1 h-1 bg-emerald-500" />
                  Escrow Payments
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-1 h-1 bg-emerald-500" />
                  Smart Contracts
                </div>
              </div>
            </div>
            <ArrowUpRight className="absolute top-8 right-8 w-8 h-8 text-white/20 group-hover:text-emerald-500 group-hover:rotate-45 transition-all" />
          </div>

          {/* TALL CARD: ANALYTICS */}
          <div className="lg:col-span-4 bg-zinc-950 p-12 md:p-16 relative group border-l border-white/10">
            <div className="h-full flex flex-col justify-between">
              <div>
                <BarChart3
                  className="w-10 h-10 text-emerald-500 mb-8"
                  strokeWidth={1}
                />
                <h3 className="text-3xl font-bold mb-4">Analytics Hub</h3>
                <p className="text-zinc-400 leading-relaxed">
                  Track your revenue, engagement, and growth across all platforms
                  in one unified dashboard.
                </p>
              </div>
              <div className="mt-12 pt-12 border-t border-white/10">
                <div className="flex justify-between items-center text-xs font-mono uppercase tracking-widest">
                  <span>Monthly Growth</span>
                  <span className="text-emerald-500">+47%</span>
                </div>
                <div className="w-full bg-zinc-900 h-1 mt-4">
                  <div className="bg-emerald-500 h-full w-[47%]" />
                </div>
              </div>
            </div>
          </div>

          {/* CARD: AFFILIATE */}
          <div className="lg:col-span-4 bg-zinc-950 p-12 relative group border-t border-white/10">
            <DollarSign className="w-10 h-10 text-emerald-500 mb-8" strokeWidth={1} />
            <h3 className="text-2xl font-bold mb-4">Affiliate System</h3>
            <p className="text-sm text-zinc-400 leading-relaxed mb-8">
              Get unique tracking links for every brand. Earn commission on every
              sale you drive. Passive income, automated.
            </p>
            <Link
              to="/register"
              className="inline-block border-b border-emerald-500/50 pb-1 text-xs font-mono uppercase tracking-widest text-emerald-500 hover:border-emerald-500 transition-colors"
            >
              Start Earning
            </Link>
          </div>

          {/* CARD: CREATOR VALUE */}
          <div className="lg:col-span-4 bg-zinc-950 p-12 relative group border-t border-l border-white/10">
            <Zap className="w-10 h-10 text-emerald-500 mb-8" strokeWidth={1} />
            <h3 className="text-2xl font-bold mb-4">Know Your Worth</h3>
            <p className="text-sm text-zinc-400 leading-relaxed mb-8">
              Our AI analyzes your reach, engagement, and niche to estimate your
              fair market rate. Never undersell again.
            </p>
            <Link
              to="/register"
              className="inline-block border-b border-emerald-500/50 pb-1 text-xs font-mono uppercase tracking-widest text-emerald-500 hover:border-emerald-500 transition-colors"
            >
              Check Your Value
            </Link>
          </div>

          {/* CARD: BRAND CONNECT */}
          <div className="lg:col-span-4 bg-emerald-500 text-black p-12 relative group border-t border-l border-white/10 hover:bg-emerald-400 transition-colors">
            <div className="absolute top-6 right-6 px-2 py-1 bg-black text-emerald-500 text-[10px] font-mono uppercase tracking-widest">
              New
            </div>
            <h3 className="text-2xl font-bold mb-4 mt-8">Brand Discovery</h3>
            <p className="text-sm text-black/70 leading-relaxed mb-8">
              Get discovered by top brands. Your profile, your rates, your terms.
            </p>
            <ArrowUpRight className="w-6 h-6" />
          </div>
        </div>
      </section>

      {/* FOR CREATORS SECTION */}
      <section id="creators" className="py-32 border-t border-white/5">
        <div className="max-w-[1800px] mx-auto px-6">
          <div className="grid lg:grid-cols-2 gap-16 items-center">
            <div>
              <div className="text-xs font-mono uppercase tracking-widest text-emerald-500 mb-4">
                For Creators
              </div>
              <h2 className="text-5xl md:text-6xl font-bold tracking-tighter mb-8">
                STOP CHASING <br />
                <span className="text-zinc-500">START CLOSING</span>
              </h2>
              <p className="text-xl text-zinc-400 leading-relaxed mb-12 max-w-lg">
                Brands come to you. View offers, negotiate terms, and secure deals
                with built-in payment protection. 30% upfront, held in escrow.
              </p>
              <div className="space-y-6">
                {[
                  "Receive campaign offers directly",
                  "AI-powered rate recommendations",
                  "Secure escrow payment system",
                  "Contract templates included",
                ].map((item, i) => (
                  <div key={i} className="flex items-center gap-4">
                    <div className="w-6 h-6 bg-emerald-500/20 flex items-center justify-center">
                      <div className="w-2 h-2 bg-emerald-500" />
                    </div>
                    <span className="text-zinc-300">{item}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="relative">
              <div className="bg-zinc-900 border border-white/10 p-8">
                <div className="flex items-center justify-between mb-6 pb-4 border-b border-white/10">
                  <span className="text-xs font-mono uppercase tracking-widest text-zinc-500">
                    Incoming Offer
                  </span>
                  <span className="px-2 py-1 bg-emerald-500/20 text-emerald-500 text-xs font-mono">
                    NEW
                  </span>
                </div>
                <div className="space-y-4">
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Brand</span>
                    <span className="text-white">Nike Athletics</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Campaign</span>
                    <span className="text-white">Summer Collection</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Deliverables</span>
                    <span className="text-white">3 Posts, 2 Stories</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Offer Amount</span>
                    <span className="text-emerald-500 text-xl font-bold">$15,000</span>
                  </div>
                </div>
                <div className="mt-6 pt-4 border-t border-white/10">
                  <div className="text-xs text-zinc-500 mb-2">Your estimated value for this reach:</div>
                  <div className="text-lg text-white">$12,000 - $18,000</div>
                </div>
                <div className="flex gap-4 mt-6">
                  <button className="flex-1 py-3 bg-emerald-500 text-black font-mono text-xs uppercase tracking-widest hover:bg-emerald-400 transition-colors">
                    Accept
                  </button>
                  <button className="flex-1 py-3 border border-white/20 text-white font-mono text-xs uppercase tracking-widest hover:bg-white/10 transition-colors">
                    Counter
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* FOR BRANDS SECTION */}
      <section id="brands" className="py-32 border-t border-white/5 bg-zinc-900/50">
        <div className="max-w-[1800px] mx-auto px-6">
          <div className="grid lg:grid-cols-2 gap-16 items-center">
            <div className="order-2 lg:order-1">
              <div className="bg-black border border-white/10 p-8">
                <div className="flex items-center justify-between mb-6 pb-4 border-b border-white/10">
                  <span className="text-xs font-mono uppercase tracking-widest text-zinc-500">
                    Campaign Builder
                  </span>
                </div>
                <div className="space-y-6">
                  <div>
                    <label className="text-xs font-mono uppercase tracking-widest text-zinc-500 block mb-2">
                      Campaign Name
                    </label>
                    <div className="py-2 border-b border-white/20 text-white">
                      Summer Product Launch
                    </div>
                  </div>
                  <div>
                    <label className="text-xs font-mono uppercase tracking-widest text-zinc-500 block mb-2">
                      Budget
                    </label>
                    <div className="py-2 border-b border-white/20 text-emerald-500 font-bold">
                      $50,000
                    </div>
                  </div>
                  <div>
                    <label className="text-xs font-mono uppercase tracking-widest text-zinc-500 block mb-2">
                      Target Creators
                    </label>
                    <div className="flex gap-2 flex-wrap">
                      {["Fitness", "Lifestyle", "100K+ Followers"].map((tag) => (
                        <span
                          key={tag}
                          className="px-3 py-1 bg-white/10 text-zinc-300 text-xs"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="pt-4">
                    <div className="text-xs font-mono uppercase tracking-widest text-zinc-500 mb-4">
                      Selected Creators (3/10)
                    </div>
                    <div className="space-y-2">
                      {["@fitness_pro", "@lifestyle_queen", "@workout_daily"].map((handle) => (
                        <div
                          key={handle}
                          className="flex items-center justify-between py-2 border-b border-white/5"
                        >
                          <span className="text-white">{handle}</span>
                          <span className="text-xs text-zinc-500">Pending</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div className="order-1 lg:order-2">
              <div className="text-xs font-mono uppercase tracking-widest text-emerald-500 mb-4">
                For Brands & Agencies
              </div>
              <h2 className="text-5xl md:text-6xl font-bold tracking-tighter mb-8">
                FIND TALENT <br />
                <span className="text-zinc-500">CLOSE DEALS</span>
              </h2>
              <p className="text-xl text-zinc-400 leading-relaxed mb-12 max-w-lg">
                Create campaigns, set your budget, and send offers to up to 10
                creators at once. First to accept locks the deal.
              </p>
              <div className="space-y-6">
                {[
                  "Search verified creator database",
                  "Limit order style offers",
                  "Payment protection via escrow",
                  "Built-in contract management",
                ].map((item, i) => (
                  <div key={i} className="flex items-center gap-4">
                    <div className="w-6 h-6 bg-emerald-500/20 flex items-center justify-center">
                      <div className="w-2 h-2 bg-emerald-500" />
                    </div>
                    <span className="text-zinc-300">{item}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* STATS */}
      <section className="py-32 border-t border-white/5">
        <div className="max-w-[1800px] mx-auto px-6 grid grid-cols-2 md:grid-cols-4 gap-12">
          {[
            { label: "Creators", value: "10K+" },
            { label: "Brands", value: "500+" },
            { label: "Deals Closed", value: "$2M+" },
            { label: "Avg. Deal Size", value: "$8K" },
          ].map((stat, i) => (
            <div key={i} className="border-l border-emerald-500/30 pl-6">
              <div className="text-xs font-mono uppercase tracking-widest text-zinc-500 mb-2">
                {stat.label}
              </div>
              <div className="text-4xl font-light text-emerald-500">{stat.value}</div>
            </div>
          ))}
        </div>
      </section>

      <footer className="bg-emerald-500 text-black py-24 px-6">
        <div className="max-w-[1800px] mx-auto">
          <div className="flex flex-col md:flex-row justify-between items-start gap-12">
            <div>
              <h2 className="text-6xl md:text-8xl font-bold tracking-tighter leading-none mb-8">
                READY TO <br /> LEVEL UP?
              </h2>
              <Link
                to="/register"
                className="inline-block px-8 py-4 bg-black text-emerald-500 font-mono uppercase tracking-widest hover:bg-zinc-800 transition-colors"
              >
                Join GumFit
              </Link>
            </div>

            <div className="grid grid-cols-2 gap-12 text-sm font-mono uppercase tracking-widest">
              <div className="space-y-4">
                <a href="#" className="block hover:underline">
                  For Creators
                </a>
                <a href="#" className="block hover:underline">
                  For Brands
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
                  Instagram
                </a>
                <a href="#" className="block hover:underline">
                  TikTok
                </a>
              </div>
            </div>
          </div>

          <div className="mt-24 pt-8 border-t border-black/20 flex justify-between items-center text-xs font-mono uppercase tracking-widest opacity-70">
            <span>© 2024 GumFit Inc.</span>
            <span>Creator Economy Platform</span>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default GumFitLanding;
