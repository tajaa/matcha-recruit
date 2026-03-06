import { m, type Variants } from "framer-motion";
import { MapPin, Shield, Zap, Search, Globe, Users, Activity, LayoutDashboard } from "lucide-react";
import { TelemetryBadge } from "../components/TelemetryBadge";
import { TechnicalSpecs } from "../components/TechnicalSpecs";
import { JurisdictionRows } from "../components/JurisdictionRows";
import { useInViewport } from "../hooks/useInViewport";
import { fonts } from "../constants";

export const Compliance = () => {
  const { ref: sectionRef, isVisible } = useInViewport();
  const containerVariants: Variants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.2,
      },
    },
  };

  const textVariants: Variants = {
    hidden: { opacity: 0, x: -40, filter: "blur(8px)" },
    visible: { 
      opacity: 1, 
      x: 0, 
      filter: "blur(0px)",
      transition: { duration: 0.8, ease: "easeOut" }
    },
  };

  const locations = [
    { name: "San Francisco, CA", count: 412, status: "OK", load: 0.8 },
    { name: "New York, NY", count: 285, status: "OK", load: 0.6 },
    { name: "Austin, TX", count: 140, status: "WARN", load: 0.4 },
    { name: "London, UK", count: 89, status: "OK", load: 0.2 },
    { name: "Remote (Global)", count: 534, status: "SYNC", load: 0.9 },
  ];

  return (
    <m.section 
      variants={containerVariants}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: "-100px" }}
      className="compliance-trigger py-64 px-6 md:px-16 lg:px-32 relative border-t border-white/5 bg-[#0A0E0C] overflow-hidden"
    >
      <div ref={sectionRef} />

      <div className="relative z-10 max-w-[1600px] mx-auto grid lg:grid-cols-2 gap-32 items-center">
        
        {/* Text Content (Left Side) */}
        <div className="space-y-16 pr-12">
          <m.div variants={textVariants} className="space-y-6">
            <div className="flex items-center gap-4">
              <div className="space-y-4">
                <span className="text-[10px] font-mono uppercase tracking-[0.3em] text-[#4ADE80]">
                  Stop finding out about law changes from your lawyer.
                </span>
                <h2
                  className="text-5xl md:text-7xl font-bold tracking-tighter leading-[0.9]"
                  style={{ fontFamily: fonts.display, letterSpacing: '0.05em' }}
                >
                  EVERY LOCATION. <br />
                  <span
                    className="italic text-zinc-500 font-light lowercase"
                    style={{ fontFamily: fonts.serif, letterSpacing: 'normal' }}
                  >
                    Every Law.
                  </span>
                </h2>
              </div>
              <TechnicalSpecs
                title="Jurisdiction Matrix"
                specs={[
                  "Automated Wage & Hour reconciliation",
                  "Geospatial law monitoring (Real-time)",
                  "Multi-tier dependency resolution",
                  "Native algorithmic enforcement"
                ]}
              />
            </div>
          </m.div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-12">
            <m.div variants={textVariants} className="space-y-4">
              <div className="w-10 h-10 rounded-full bg-white/5 flex items-center justify-center">
                <Globe size={18} className="text-white" />
              </div>
              <h4 className="text-sm font-bold uppercase tracking-widest font-mono text-white">
                Macro View
              </h4>
              <p className="text-xs text-zinc-500 leading-relaxed font-mono">
                Aggregate compliance statuses across multiple geographical nodes instantly.
              </p>
            </m.div>
            <m.div variants={textVariants} className="space-y-4">
              <div className="w-10 h-10 rounded-full bg-white/5 flex items-center justify-center">
                <Users size={18} className="text-white" />
              </div>
              <h4 className="text-sm font-bold uppercase tracking-widest font-mono text-white">
                Impact Radius
              </h4>
              <p className="text-xs text-zinc-500 leading-relaxed font-mono">
                See exact headcount exposure for every local and state-level regulatory shift.
              </p>
            </m.div>
            <m.div variants={textVariants} className="space-y-4">
              <div className="w-10 h-10 rounded-full bg-white/5 flex items-center justify-center">
                <Zap size={18} className="text-white" />
              </div>
              <h4 className="text-sm font-bold uppercase tracking-widest font-mono text-white">
                Live Adaptation
              </h4>
              <p className="text-xs text-zinc-500 leading-relaxed font-mono">
                When a city updates its minimum wage, your entire workforce infrastructure adapts in the same pay period.
              </p>
            </m.div>
            <m.div variants={textVariants} className="space-y-4">
              <div className="w-10 h-10 rounded-full bg-white/5 flex items-center justify-center">
                <Shield size={18} className="text-white" />
              </div>
              <h4 className="text-sm font-bold uppercase tracking-widest font-mono text-white">
                Safe Harbor Sync
              </h4>
              <p className="text-xs text-zinc-500 leading-relaxed font-mono">
                Every policy is verified against the highest standard of employee protection to minimize litigation risk.
              </p>
            </m.div>
          </div>
        </div>

        {/* Visual Matrix Stack (Right Side) */}
        <m.div 
          initial={{ opacity: 0, scale: 0.9, x: 50 }}
          whileInView={{ opacity: 1, scale: 1, x: 0 }}
          transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
          viewport={{ once: true }}
          className="relative z-10 flex flex-col gap-8"
        >
          {/* Jurisdiction Feed Modal */}
          <div className="bg-[#060906] rounded-2xl border border-white/10 p-6 shadow-[0_0_100px_rgba(0,0,0,0.8)] overflow-hidden relative group">
            <div
              style={{ animation: isVisible ? "landing-scan-down 3s ease-in-out infinite" : "none" }}
              className="absolute left-0 right-0 h-[1px] bg-[#4ADE80]/30 shadow-[0_0_20px_#4ADE80] z-30"
            />

            <div className="flex justify-between items-center mb-4 border-b border-white/10 pb-4">
              <div className="flex items-center gap-3">
                <div className="p-1.5 bg-[#4ADE80]/10 rounded">
                  <MapPin className="w-4 h-4 text-[#4ADE80]" />
                </div>
                <div>
                  <span className="block text-[9px] font-mono uppercase tracking-widest text-white font-bold">
                    Jurisdiction Matrix
                  </span>
                  <span className="text-[7px] font-mono text-[#F0EFEA]/30 uppercase tracking-[0.2em]">
                    Real-time Enforcement Feed
                  </span>
                </div>
              </div>
              <TelemetryBadge text="Live" active />
            </div>

            <JurisdictionRows />
          </div>
          
          {/* Fleet Overview Modal */}
          <div className="bg-black border border-white/10 p-6 shadow-[0_0_80px_rgba(255,255,255,0.015)] group rounded-2xl overflow-hidden relative">
            
            {/* Header */}
            <div className="flex justify-between items-center border-b border-white/10 pb-4 mb-4 z-10 relative">
              <div className="flex items-center gap-3">
                <div className="p-1.5 bg-white/5 rounded">
                  <LayoutDashboard size={14} className="text-zinc-400" />
                </div>
                <div>
                  <span className="block text-[9px] font-mono uppercase tracking-widest text-white font-bold">
                    Fleet Overview
                  </span>
                  <span className="text-[7px] font-mono text-[#F0EFEA]/30 uppercase tracking-[0.2em]">
                    Active Work Nodes
                  </span>
                </div>
              </div>
              <span className="text-[8px] text-zinc-500 uppercase tracking-widest flex items-center gap-2">
                <Activity size={10} className="text-zinc-400" /> Live Data
              </span>
            </div>

            {/* Grid Map / Data Table */}
            <div className="w-full font-mono text-[9px] uppercase tracking-widest text-zinc-400 z-10 relative">
              
              <div className="flex border-b border-white/5 pb-2 text-[7px] text-zinc-600">
                <span className="w-1/3">Node</span>
                <span className="w-1/4 text-right">Headcount</span>
                <span className="w-1/4 text-center">Load</span>
                <span className="w-1/6 text-right">Status</span>
              </div>

              {locations.map((loc, i) => (
                <div key={i} className="flex items-center py-3 border-b border-white/5 hover:bg-white/[0.02] transition-colors -mx-4 px-4">
                  <span className="w-1/3 text-white truncate pr-2">{loc.name}</span>
                  <span className="w-1/4 text-right">{loc.count.toString().padStart(4, "0")}</span>
                  
                  <div className="w-1/4 flex justify-center px-4">
                    <div className="w-full h-1 bg-white/10 rounded-full overflow-hidden flex">
                      <m.div 
                        initial={{ width: 0 }}
                        whileInView={{ width: `${loc.load * 100}%` }}
                        transition={{ duration: 1, delay: i * 0.15 }}
                        className="h-full bg-zinc-400"
                      />
                    </div>
                  </div>

                  <span className={`w-1/6 text-right font-bold ${
                    loc.status === "OK" ? "text-white/60" :
                    loc.status === "WARN" ? `text-white ${isVisible ? "animate-pulse" : ""}` :
                    "text-zinc-600"
                  }`}>
                    {loc.status}
                  </span>
                </div>
              ))}
            </div>

            {/* Scanning Overlay */}
            <div
              style={{ animation: isVisible ? "landing-pulse-opacity 3s ease-in-out infinite" : "none" }}
              className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,rgba(255,255,255,0.05)_0%,transparent_70%)] pointer-events-none z-0"
            />
          </div>

        </m.div>
      </div>
    </m.section>
  );
};
