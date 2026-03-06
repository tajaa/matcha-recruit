import { forwardRef } from "react";
import { m, type Variants } from "framer-motion";
import { Radar, Activity, ShieldCheck, ShieldAlert, Target, AlertTriangle } from "lucide-react";
import { TelemetryBadge } from "../components/TelemetryBadge";
import { TechnicalSpecs } from "../components/TechnicalSpecs";
import { fonts } from "../constants";

export const RiskSnapshot = forwardRef<HTMLDivElement>((_, ref) => {
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

  return (
    <m.section
      ref={ref}
      variants={containerVariants}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: "-100px" }}
      className="risk-snapshot-trigger py-64 px-6 md:px-16 lg:px-32 relative bg-[#060807] overflow-hidden border-t border-white/5"
    >
      {/* Background Depth */}
      <div className="absolute inset-0 z-0 pointer-events-none">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[1000px] h-[1000px] bg-white/[0.01] rounded-full blur-[100px] mix-blend-screen" />
      </div>

      <div className="max-w-[1600px] mx-auto grid lg:grid-cols-2 gap-32 items-center relative z-10">
        
        <div className="space-y-12 pr-12">
          <m.div variants={featureVariants} className="flex items-center gap-4">
            <TelemetryBadge text="Active Surveillance" active={true} />
            <TechnicalSpecs 
              title="Threat Detection"
              specs={[
                "Continuous state synchronization",
                "Heuristic risk mapping",
                "Automated gap analysis",
                "Real-time compliance alerts"
              ]}
            />
          </m.div>

          <m.h2
            variants={featureVariants}
            className="text-6xl md:text-8xl font-bold tracking-tighter leading-[0.85]"
            style={{ fontFamily: fonts.display, letterSpacing: '0.05em' }}
          >
            RISK <br />
            <span
              className="italic text-zinc-500 font-light lowercase"
              style={{ fontFamily: fonts.serif, letterSpacing: 'normal' }}
            >
              Snapshot.
            </span>
          </m.h2>

          <m.div variants={featureVariants} className="space-y-6">
            <p className="text-zinc-500 text-xl md:text-2xl font-light leading-relaxed max-w-xl" style={{ fontFamily: fonts.sans }}>
              The biggest risk is the one you don’t see coming. 
            </p>
            <p className="text-zinc-400 text-base md:text-lg font-light leading-relaxed max-w-xl" style={{ fontFamily: fonts.sans }}>
              Identify and neutralize compliance gaps before they escalate. Our heuristic engine acts as an early warning system, mapping your footprint to provide a real-time threat matrix.
            </p>
          </m.div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-12 gap-y-10 pt-8 border-t border-white/5">
            <m.div variants={featureVariants} className="space-y-4 group">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-white/5 text-white group-hover:bg-white group-hover:text-black transition-colors">
                  <Radar size={20} />
                </div>
                <h4 className="font-bold text-white uppercase tracking-[0.2em] text-xs font-mono">
                  Continuous Sweep
                </h4>
              </div>
              <p className="text-zinc-500 text-sm leading-relaxed border-l border-white/10 pl-4 font-mono">
                Constant surveillance of active operations against local regulations.
              </p>
            </m.div>

            <m.div variants={featureVariants} className="space-y-4 group">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-white/5 text-white group-hover:bg-white group-hover:text-black transition-colors">
                  <Activity size={20} />
                </div>
                <h4 className="font-bold text-white uppercase tracking-[0.2em] text-xs font-mono">
                  Early Warning
                </h4>
              </div>
              <p className="text-zinc-500 text-sm leading-relaxed border-l border-white/10 pl-4 font-mono">
                Proactive alerts for pending compliance deadlines and exposure risks.
              </p>
            </m.div>

            <m.div variants={featureVariants} className="space-y-4 group">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-white/5 text-white group-hover:bg-white group-hover:text-black transition-colors">
                  <ShieldAlert size={20} />
                </div>
                <h4 className="font-bold text-white uppercase tracking-[0.2em] text-xs font-mono">
                  Gap Analysis
                </h4>
              </div>
              <p className="text-zinc-500 text-sm leading-relaxed border-l border-white/10 pl-4 font-mono">
                Instantly identify discrepancies between active policies and legal requirements.
              </p>
            </m.div>

            <m.div variants={featureVariants} className="space-y-4 group">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-white/5 text-white group-hover:bg-white group-hover:text-black transition-colors">
                  <Target size={20} />
                </div>
                <h4 className="font-bold text-white uppercase tracking-[0.2em] text-xs font-mono">
                  Threat Routing
                </h4>
              </div>
              <p className="text-zinc-500 text-sm leading-relaxed border-l border-white/10 pl-4 font-mono">
                Automatically prioritize risks based on financial impact and probability.
              </p>
            </m.div>
          </div>
        </div>

        <m.div 
          initial={{ opacity: 0, scale: 0.9, x: 50 }}
          whileInView={{ opacity: 1, scale: 1, x: 0 }}
          transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
          className="relative mt-20 lg:mt-0"
        >
          {/* Floating Alert Panels */}
          <m.div 
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.8, duration: 0.6 }}
            className="absolute -top-10 -left-6 lg:-left-12 bg-black/90 backdrop-blur-md border border-zinc-800 p-4 rounded-xl shadow-[0_20px_40px_rgba(0,0,0,0.8)] z-30 hidden md:block w-56"
          >
            <div className="flex items-center gap-3 mb-3 border-b border-white/10 pb-2">
              <AlertTriangle size={14} className="text-amber-500 animate-pulse" />
              <span className="text-[9px] font-mono uppercase tracking-widest text-zinc-400">Threat Detected</span>
            </div>
            <p className="text-[10px] text-white font-mono uppercase tracking-wider mb-1">NY Pay Transparency</p>
            <p className="text-[8px] text-zinc-500 font-mono uppercase tracking-widest">Exposure: High</p>
          </m.div>
          
          <m.div 
            initial={{ opacity: 0, y: -20 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ delay: 1.2, duration: 0.6 }}
            className="absolute -bottom-10 -right-6 lg:-right-12 bg-black/90 backdrop-blur-md border border-zinc-800 p-4 rounded-xl shadow-[0_20px_40px_rgba(0,0,0,0.8)] z-30 hidden md:block w-56"
          >
            <div className="flex items-center gap-3 mb-3 border-b border-white/10 pb-2">
              <ShieldCheck size={14} className="text-zinc-500" />
              <span className="text-[9px] font-mono uppercase tracking-widest text-zinc-400">Status Update</span>
            </div>
            <p className="text-[10px] text-white font-mono uppercase tracking-wider mb-1">CA Meal Breaks</p>
            <p className="text-[8px] text-zinc-500 font-mono uppercase tracking-widest">Mitigated</p>
          </m.div>

          {/* Radar / Snapshot Visual */}
          <div className="relative aspect-square max-w-lg mx-auto bg-[#0A0E0C] border border-white/10 flex items-center justify-center p-12 overflow-hidden shadow-[0_0_80px_rgba(255,255,255,0.02)] group rounded-full">
            
            {/* Radar Sweep */}
            <div className="absolute inset-0 z-0">
              <div
                className="w-full h-full rounded-full"
                style={{
                  background: "conic-gradient(from 0deg, transparent 70%, rgba(255,255,255,0.08) 100%)",
                  animation: "spin 6s linear infinite",
                }}
              />
            </div>

            {/* Concentric Circles */}
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="w-[80%] h-[80%] border border-white/5 rounded-full" />
              <div className="w-[60%] h-[60%] border border-white/5 rounded-full absolute" />
              <div className="w-[40%] h-[40%] border border-white/10 rounded-full absolute" />
              <div className="w-[20%] h-[20%] border border-white/20 rounded-full absolute bg-white/5" />
            </div>

            {/* Crosshairs */}
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="w-full h-[1px] bg-white/5" />
              <div className="h-full w-[1px] bg-white/5 absolute" />
            </div>

            {/* Threat Nodes / Blips */}
            <div className="absolute inset-0 z-10">
              {[
                { top: "30%", left: "65%", delay: 0 },
                { top: "75%", left: "35%", delay: 1.5 },
                { top: "45%", left: "20%", delay: 3 },
                { top: "25%", left: "35%", delay: 4.5 },
              ].map((pos, i) => (
                <div
                  key={i}
                  className="absolute w-2 h-2 bg-white rounded-full"
                  style={{
                    top: pos.top,
                    left: pos.left,
                    animation: "landing-blip 2s ease-in-out infinite",
                    animationDelay: `${pos.delay}s`,
                  }}
                >
                  <div className="absolute inset-0 bg-white rounded-full animate-ping opacity-50" />
                </div>
              ))}
            </div>

            {/* Center Eye / Core */}
            <div className="relative z-20 flex flex-col items-center gap-3">
               <div className="bg-black border border-white/20 p-4 rounded-full shadow-[0_0_30px_rgba(255,255,255,0.1)]">
                 <ShieldCheck size={24} className="text-zinc-300" />
               </div>
               <span className="text-[9px] font-mono uppercase tracking-[0.3em] text-white/50 bg-[#0A0E0C] px-3 py-1.5 border border-white/10 rounded-full shadow-xl">
                 Scanning
               </span>
            </div>

          </div>
        </m.div>

      </div>
    </m.section>
  );
});

RiskSnapshot.displayName = "RiskSnapshot";