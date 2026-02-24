import { forwardRef } from "react";
import { motion } from "framer-motion";
import { Activity } from "lucide-react";
import { TelemetryBadge } from "../components/TelemetryBadge";
import { TechnicalSpecs } from "../components/TechnicalSpecs";
import { HorizontalAsciiEntity } from "../components/HorizontalAsciiEntity";
import { fonts } from "../constants";

export const Interviewer = forwardRef<HTMLDivElement>((_, ref) => {
  return (
    <motion.section
      ref={ref}
      initial={{ opacity: 0, scale: 0.95 }}
      whileInView={{ opacity: 1, scale: 1 }}
      viewport={{ once: true, margin: "-100px" }}
      transition={{ duration: 1, ease: [0.16, 1, 0.3, 1] }}
      className="interviewer-trigger py-40 px-6 relative bg-[#060807] overflow-hidden rounded-[3rem] mx-4 border border-white/5 shadow-2xl"
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
          <div className="flex items-center">
            <TelemetryBadge text="Autonomous Agent" />
            <TechnicalSpecs 
              title="The Interviewer"
              specs={[
                "Vocal prosody analysis",
                "Real-time speech-to-intent",
                "Latent emotion detection",
                "Dynamic conversational tree"
              ]}
            />
          </div>
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
    </motion.section>
  );
});

Interviewer.displayName = "Interviewer";
