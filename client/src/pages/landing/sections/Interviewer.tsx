import { forwardRef } from "react";
import { motion, type Variants } from "framer-motion";
import { Activity, Mic2, Brain, Waves } from "lucide-react";
import { TelemetryBadge } from "../components/TelemetryBadge";
import { TechnicalSpecs } from "../components/TechnicalSpecs";
import { HorizontalAsciiEntity } from "../components/HorizontalAsciiEntity";
import { fonts } from "../constants";

export const Interviewer = forwardRef<HTMLDivElement>((_, ref) => {
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
      className="interviewer-trigger py-64 px-6 md:px-16 lg:px-32 relative bg-[#060807] overflow-hidden rounded-[4rem] border border-white/5 shadow-2xl"
      style={{ transform: "translateZ(0)" }}
    >
      {/* Dynamic Background Data-Flow */}
      <div className="absolute inset-0 z-0 pointer-events-none opacity-20">
        <div className="absolute top-0 left-0 w-full h-full bg-[radial-gradient(circle_at_50%_50%,rgba(74,222,128,0.05)_0%,transparent_70%)]" />
        <motion.div 
          animate={{ x: ["-100%", "100%"] }}
          transition={{ duration: 10, repeat: Infinity, ease: "linear" }}
          className="w-1/2 h-px bg-gradient-to-r from-transparent via-[#4ADE80]/30 to-transparent top-1/4 absolute"
        />
        <motion.div 
          animate={{ x: ["100%", "-100%"] }}
          transition={{ duration: 15, repeat: Infinity, ease: "linear" }}
          className="w-1/2 h-px bg-gradient-to-r from-transparent via-[#D95A38]/30 to-transparent top-3/4 absolute"
        />
      </div>

      <div className="max-w-[1600px] mx-auto grid lg:grid-cols-2 gap-32 items-center relative z-10">
        <motion.div 
          initial={{ opacity: 0, scale: 0.9, x: -50 }}
          whileInView={{ opacity: 1, scale: 1, x: 0 }}
          transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
          className="order-2 lg:order-1 relative"
        >
          <div className="relative aspect-square max-w-lg mx-auto bg-white/[0.02] backdrop-blur-2xl rounded-[4rem] border border-white/10 flex flex-col items-center justify-center p-16 overflow-hidden shadow-[0_0_100px_rgba(74,222,128,0.08)] group">
            <div className="mb-16 scale-[1.4] transition-transform duration-1000 group-hover:scale-[1.5]">
              <HorizontalAsciiEntity />
            </div>
            
            <div className="w-full font-mono border-t border-white/10 pt-10">
              <div className="flex justify-between items-end mb-6">
                <div className="flex flex-col gap-2">
                  <span className="flex items-center gap-3 text-[10px] text-[#4ADE80] uppercase tracking-[0.3em] font-bold">
                    <Activity size={14} className="animate-pulse" /> Neural Voice Mesh
                  </span>
                  <span className="text-[8px] text-zinc-500 uppercase tracking-widest">
                    Prosody Stream: Active
                  </span>
                </div>
                <div className="flex gap-1.5 items-end h-8">
                  {[0.4, 0.8, 0.3, 0.9, 0.5, 0.7, 0.4].map((h, i) => (
                    <motion.div 
                      key={i}
                      animate={{ height: ["20%", "100%", "40%"] }}
                      transition={{ 
                        duration: 1 + (i * 0.2), 
                        repeat: Infinity, 
                        ease: "easeInOut" 
                      }}
                      className="w-1 bg-[#4ADE80]/40 rounded-full"
                      style={{ height: `${h * 100}%` }}
                    />
                  ))}
                </div>
              </div>
              <div className="h-1 w-full bg-white/5 rounded-full overflow-hidden">
                <motion.div 
                  animate={{ width: ["0%", "100%", "0%"] }}
                  transition={{ duration: 8, repeat: Infinity }}
                  className="h-full bg-gradient-to-r from-transparent via-[#4ADE80] to-transparent"
                />
              </div>
            </div>
          </div>
        </motion.div>

        <div className="order-1 lg:order-2 space-y-12">
          <motion.div variants={featureVariants} className="flex items-center gap-4">
            <TelemetryBadge text="Autonomous Agent" active />
            <TechnicalSpecs 
              title="Vocal Prosody Engine"
              specs={[
                "Sub-harmonic hesitation mapping",
                "Emotional valence scoring",
                "Dynamic intent reconciliation",
                "Real-time spectral analysis"
              ]}
            />
          </motion.div>

          <motion.h2
            variants={featureVariants}
            className="text-6xl md:text-8xl font-bold tracking-tighter leading-[0.85]"
            style={{ fontFamily: fonts.sans }}
          >
            THE <br />
            <span
              className="italic text-[#F0EFEA]/50 font-light"
              style={{ fontFamily: fonts.serif }}
            >
              Interviewer.
            </span>
          </motion.h2>

          <motion.p 
            variants={featureVariants}
            className="text-[#F0EFEA]/60 text-xl md:text-2xl font-light leading-relaxed max-w-xl"
          >
            Move beyond static screening forms. Our autonomous voice agents 
            conduct high-fidelity conversations that extract deep cultural 
            insights through native latent audio analysis.
          </motion.p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-12 pt-8">
            <motion.div variants={featureVariants} className="space-y-4 group">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-white/5 rounded-lg text-white group-hover:text-[#4ADE80] transition-colors">
                  <Waves size={20} />
                </div>
                <h4 className="font-bold text-[#F0EFEA] uppercase tracking-[0.2em] text-xs font-mono">
                  Prosody Mapping
                </h4>
              </div>
              <p className="text-[#F0EFEA]/50 text-sm leading-relaxed border-l border-white/5 pl-4">
                Detects confidence, hesitation, and linguistic markers invisible 
                to text-only AI models.
              </p>
            </motion.div>

            <motion.div variants={featureVariants} className="space-y-4 group">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-white/5 rounded-lg text-white group-hover:text-[#D95A38] transition-colors">
                  <Brain size={20} />
                </div>
                <h4 className="font-bold text-[#F0EFEA] uppercase tracking-[0.2em] text-xs font-mono">
                  Dynamic Probing
                </h4>
              </div>
              <p className="text-[#F0EFEA]/50 text-sm leading-relaxed border-l border-white/5 pl-4">
                Intelligently follows up on vague answers to force biological 
                honesty and technical depth.
              </p>
            </motion.div>
          </div>
          
          <motion.div variants={featureVariants} className="pt-8">
            <button className="flex items-center gap-4 group">
              <div className="w-12 h-12 rounded-full border border-white/10 flex items-center justify-center group-hover:bg-white group-hover:text-black transition-all duration-500">
                <Mic2 size={18} />
              </div>
              <span className="text-[10px] font-mono uppercase tracking-[0.3em] font-bold">
                Initialize Voice Test
              </span>
            </button>
          </motion.div>
        </div>
      </div>
    </motion.section>
  );
});

Interviewer.displayName = "Interviewer";
