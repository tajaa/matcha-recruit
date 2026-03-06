import { forwardRef } from "react";
import { m, type Variants } from "framer-motion";
import { Globe, Users, Activity, LayoutDashboard } from "lucide-react";
import { TelemetryBadge } from "../components/TelemetryBadge";
import { TechnicalSpecs } from "../components/TechnicalSpecs";
import { useInViewport } from "../hooks/useInViewport";
import { fonts } from "../constants";

export const ComplianceDashboard = forwardRef<HTMLDivElement>((_, ref) => {
  const { ref: sectionRef, isVisible } = useInViewport();
  const containerVariants: Variants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: { staggerChildren: 0.25 }
    }
  };

  const featureVariants: Variants = {
    hidden: { opacity: 0, y: 20 },
    visible: { 
      opacity: 1, 
      y: 0,
      transition: { duration: 0.6, ease: "easeOut" }
    }
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
      ref={ref}
      variants={containerVariants}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: "-100px" }}
      className="compliance-dashboard-trigger py-64 px-6 md:px-16 lg:px-32 relative bg-[#060807] overflow-hidden border-t border-white/5"
    >
      <div ref={sectionRef} />
      {/* Background Depth */}
      <div className="absolute inset-0 z-0 pointer-events-none">
        <div className="absolute top-0 right-0 w-[800px] h-[800px] rounded-full mix-blend-screen translate-x-1/3 -translate-y-1/3" style={{ background: "radial-gradient(circle, rgba(255,255,255,0.01) 0%, transparent 70%)" }} />
      </div>

      <div className="max-w-[1600px] mx-auto grid lg:grid-cols-2 gap-32 items-center relative z-10">
        
        {/* Text Content (Left Side) */}
        <div className="space-y-12 pr-12">
          <m.div variants={featureVariants} className="flex items-center gap-4">
            <TelemetryBadge text="Global Telemetry" active={true} />
            <TechnicalSpecs 
              title="Fleet Status"
              specs={[
                "Distributed workforce mapping",
                "Real-time headcounts",
                "Jurisdictional roll-ups",
                "Daily regulatory diffs"
              ]}
            />
          </m.div>

          <m.h2
            variants={featureVariants}
            className="text-6xl md:text-8xl font-bold tracking-tighter leading-[0.85]"
            style={{ fontFamily: fonts.display, letterSpacing: '0.05em' }}
          >
            COMPLIANCE <br />
            <span
              className="italic text-zinc-500 font-light lowercase"
              style={{ fontFamily: fonts.serif, letterSpacing: 'normal' }}
            >
              Dashboard.
            </span>
          </m.h2>

          <m.p 
            variants={featureVariants}
            className="text-zinc-500 text-xl md:text-2xl font-light leading-relaxed max-w-xl"
            style={{ fontFamily: fonts.sans }}
          >
            Navigate complex labor laws with a single glance.
          </m.p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-12 pt-8 border-t border-white/5">
            <m.div variants={featureVariants} className="space-y-4 group">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-white/5 text-white group-hover:bg-white group-hover:text-black transition-colors">
                  <Globe size={20} />
                </div>
                <h4 className="font-bold text-white uppercase tracking-[0.2em] text-xs font-mono">
                  Macro View
                </h4>
              </div>
              <p className="text-zinc-500 text-sm leading-relaxed border-l border-white/10 pl-4 font-mono">
                Aggregate compliance statuses across multiple geographical nodes instantly.
              </p>
            </m.div>

            <m.div variants={featureVariants} className="space-y-4 group">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-white/5 text-white group-hover:bg-white group-hover:text-black transition-colors">
                  <Users size={20} />
                </div>
                <h4 className="font-bold text-white uppercase tracking-[0.2em] text-xs font-mono">
                  Impact Radius
                </h4>
              </div>
              <p className="text-zinc-500 text-sm leading-relaxed border-l border-white/10 pl-4 font-mono">
                See exact headcount exposure for every local and state-level regulatory shift.
              </p>
            </m.div>
          </div>
        </div>

        {/* Visual Matrix (Right Side) */}
        <m.div 
          initial={{ opacity: 0, scale: 0.9, x: 50 }}
          whileInView={{ opacity: 1, scale: 1, x: 0 }}
          transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
          className="relative"
        >
          <div className="relative aspect-square max-w-lg mx-auto bg-black border border-white/10 p-8 flex flex-col shadow-[0_0_80px_rgba(255,255,255,0.015)] group rounded-2xl overflow-hidden">
            
            {/* Header */}
            <div className="flex justify-between items-center border-b border-white/10 pb-6 mb-6 z-10">
              <div className="flex items-center gap-3">
                <LayoutDashboard size={16} className="text-zinc-500" />
                <span className="text-[10px] text-white uppercase tracking-[0.3em] font-bold">
                  Fleet Overview
                </span>
              </div>
              <span className="text-[8px] text-zinc-500 uppercase tracking-widest flex items-center gap-2">
                <Activity size={10} className="text-zinc-400" /> Live Data
              </span>
            </div>

            {/* Grid Map / Data Table */}
            <div className="flex-1 flex flex-col justify-between z-10 w-full font-mono text-[9px] uppercase tracking-widest text-zinc-400">
              
              <div className="flex border-b border-white/5 pb-2 text-[7px] text-zinc-600">
                <span className="w-1/3">Node</span>
                <span className="w-1/4 text-right">Headcount</span>
                <span className="w-1/4 text-center">Load</span>
                <span className="w-1/6 text-right">Status</span>
              </div>

              {locations.map((loc, i) => (
                <div key={i} className="flex items-center py-4 border-b border-white/5 hover:bg-white/[0.02] transition-colors -mx-4 px-4">
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

              <div className="pt-4 flex justify-between items-center text-[7px] text-zinc-600">
                <span>Total Active Nodes: {locations.length}</span>
                <span>System: Nominal</span>
              </div>
            </div>

            {/* Scanning Overlay */}
            <div
              style={{ animation: isVisible ? "landing-pulse-opacity 3s ease-in-out infinite" : "none" }}
              className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,rgba(255,255,255,0.1)_0%,transparent_70%)] pointer-events-none"
            />
            
          </div>
        </m.div>

      </div>
    </m.section>
  );
});

ComplianceDashboard.displayName = "ComplianceDashboard";
