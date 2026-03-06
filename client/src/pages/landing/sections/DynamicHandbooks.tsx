import { forwardRef } from "react";
import { motion, type Variants } from "framer-motion";
import { BookMarked, RefreshCw, FileCode2, History } from "lucide-react";
import { TelemetryBadge } from "../components/TelemetryBadge";
import { TechnicalSpecs } from "../components/TechnicalSpecs";
import { fonts } from "../constants";

export const DynamicHandbooks = forwardRef<HTMLDivElement>((_, ref) => {
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
    <motion.section
      ref={ref}
      variants={containerVariants}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: "-100px" }}
      className="dynamic-handbooks-trigger py-64 px-6 md:px-16 lg:px-32 relative bg-[#0A0E0C] overflow-hidden"
    >
      {/* Background Depth */}
      <div className="absolute inset-0 z-0 pointer-events-none opacity-[0.03]">
        <div className="absolute top-0 left-0 w-full h-full bg-[url('https://www.transparenttextures.com/patterns/asfalt-light.png')]" />
      </div>

      <div className="max-w-[1600px] mx-auto grid lg:grid-cols-2 gap-32 items-center relative z-10">
        
        {/* Visual Matrix (Left Side) */}
        <motion.div 
          initial={{ opacity: 0, scale: 0.9, x: -50 }}
          whileInView={{ opacity: 1, scale: 1, x: 0 }}
          transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
          className="order-2 lg:order-1 relative"
        >
          <div className="relative aspect-[4/3] max-w-lg mx-auto bg-black border border-white/10 flex flex-col p-8 overflow-hidden shadow-[0_0_80px_rgba(255,255,255,0.02)] group">
            
            {/* Header */}
            <div className="flex justify-between items-center border-b border-white/10 pb-4 mb-6 z-10">
              <div className="flex items-center gap-3">
                <FileCode2 size={16} className="text-zinc-500" />
                <span className="text-[10px] text-white uppercase tracking-[0.3em] font-bold">
                  Policy Compiler
                </span>
              </div>
              <span className="text-[8px] text-zinc-500 uppercase tracking-widest flex items-center gap-2">
                <RefreshCw size={10} className="animate-spin" /> Syncing
              </span>
            </div>

            {/* Document Lines Simulation */}
            <div className="flex-1 flex flex-col gap-3 z-10 font-mono text-[8px] sm:text-[10px] text-zinc-600 uppercase tracking-widest relative">
              {[
                { w: "80%", type: "static" },
                { w: "95%", type: "static" },
                { w: "40%", type: "static" },
                { w: "100%", type: "diff-remove", label: "DEL: SECTION 4.A (OBSOLETE)" },
                { w: "100%", type: "diff-add", label: "ADD: JURISDICTION OVERRIDE (NY)" },
                { w: "85%", type: "static" },
                { w: "60%", type: "static" },
              ].map((line, i) => (
                <div key={i} className="flex items-center gap-4 group/line">
                  {line.type === "static" ? (
                    <div className="h-2 bg-white/5 rounded-full" style={{ width: line.w }} />
                  ) : (
                    <motion.div 
                      initial={{ opacity: 0, x: -10 }}
                      whileInView={{ opacity: 1, x: 0 }}
                      transition={{ duration: 0.5, delay: i * 0.2 }}
                      className={`flex-1 p-2 border-l-2 flex flex-col gap-2 ${
                        line.type === "diff-add" ? "border-white bg-white/5" : "border-zinc-700 bg-zinc-900/30 line-through opacity-50"
                      }`}
                    >
                      <span className={line.type === "diff-add" ? "text-white" : "text-zinc-500"}>
                        {line.label}
                      </span>
                      {line.type === "diff-add" && (
                        <div className="space-y-1">
                          <div className="h-1 bg-white/20 rounded-full w-[90%]" />
                          <div className="h-1 bg-white/20 rounded-full w-[70%]" />
                        </div>
                      )}
                    </motion.div>
                  )}
                </div>
              ))}

              {/* Scanning Laser */}
              <motion.div
                animate={{ top: ["0%", "100%", "0%"] }}
                transition={{ duration: 4, repeat: Infinity, ease: "linear" }}
                className="absolute left-0 w-full h-[1px] bg-white/40 shadow-[0_0_10px_rgba(255,255,255,0.5)] z-20 pointer-events-none"
              />
            </div>
            
          </div>
        </motion.div>

        {/* Text Content (Right Side) */}
        <div className="order-1 lg:order-2 space-y-12">
          <motion.div variants={featureVariants} className="flex items-center gap-4">
            <TelemetryBadge text="Living Documents" active={false} />
            <TechnicalSpecs 
              title="Compilation Engine"
              specs={[
                "Jurisdictional branching",
                "Automated version control",
                "Real-time state diffing",
                "Dynamic signature routing"
              ]}
            />
          </motion.div>

          <motion.h2
            variants={featureVariants}
            className="text-6xl md:text-8xl font-bold tracking-tighter leading-[0.85]"
            style={{ fontFamily: fonts.display, letterSpacing: '0.05em' }}
          >
            DYNAMIC <br />
            <span
              className="italic text-zinc-500 font-light lowercase"
              style={{ fontFamily: fonts.serif, letterSpacing: 'normal' }}
            >
              Handbooks.
            </span>
          </motion.h2>

          <motion.p 
            variants={featureVariants}
            className="text-zinc-500 text-xl md:text-2xl font-light leading-relaxed max-w-xl"
            style={{ fontFamily: fonts.sans }}
          >
            Always up-to-date, always compliant.
          </motion.p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-12 pt-8 border-t border-white/5">
            <motion.div variants={featureVariants} className="space-y-4 group">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-white/5 text-white group-hover:bg-white group-hover:text-black transition-colors">
                  <BookMarked size={20} />
                </div>
                <h4 className="font-bold text-white uppercase tracking-[0.2em] text-xs font-mono">
                  Foundational Build
                </h4>
              </div>
              <p className="text-zinc-500 text-sm leading-relaxed border-l border-white/10 pl-4 font-mono">
                Generate comprehensive, state-specific policies tailored to your operational footprint.
              </p>
            </motion.div>

            <motion.div variants={featureVariants} className="space-y-4 group">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-white/5 text-white group-hover:bg-white group-hover:text-black transition-colors">
                  <History size={20} />
                </div>
                <h4 className="font-bold text-white uppercase tracking-[0.2em] text-xs font-mono">
                  Law-Triggered Updates
                </h4>
              </div>
              <p className="text-zinc-500 text-sm leading-relaxed border-l border-white/10 pl-4 font-mono">
                When legislation shifts, your handbook suggests an exact diff to maintain compliance.
              </p>
            </motion.div>
          </div>
        </div>

      </div>
    </motion.section>
  );
});

DynamicHandbooks.displayName = "DynamicHandbooks";
