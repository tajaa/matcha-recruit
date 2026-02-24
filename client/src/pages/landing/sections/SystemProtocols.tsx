import { forwardRef } from "react";
import { motion } from "framer-motion";
import { ERInferenceEngine } from "../components/ERInferenceEngine";
import { PolicyMatrixScanner } from "../components/PolicyMatrixScanner";
import { IncidentAuditRing } from "../components/IncidentAuditRing";
import { TechnicalSpecs } from "../components/TechnicalSpecs";
import { fonts } from "../constants";

export const SystemProtocols = forwardRef<HTMLDivElement>((_, ref) => {
  const cardVariants = {
    offscreen: { y: 100, opacity: 0, scale: 0.95 },
    onscreen: { 
      y: 0, 
      opacity: 1, 
      scale: 1,
      transition: { 
        type: "spring", 
        bounce: 0.2, 
        duration: 1.2 
      } 
    }
  };

  return (
    <section ref={ref} className="system-trigger relative mt-64 space-y-32 px-6 md:px-16 lg:px-32 pb-64">
      {/* Card 1: Obsidian (ER Copilot) */}
      <motion.div 
        initial="offscreen"
        whileInView="onscreen"
        viewport={{ once: true, amount: 0.3 }}
        variants={cardVariants}
        className="system-card sticky top-32 min-h-[80vh] w-full flex items-center justify-center p-12 bg-[#0A0E0C] border border-white/10 rounded-[4rem] origin-top z-10 shadow-2xl"
      >
        <div className="max-w-[1600px] w-full grid grid-cols-1 md:grid-cols-2 gap-32 items-center">
          <div className="space-y-12">
            <div className="flex items-center gap-6">
              <div className="text-[10px] uppercase tracking-[0.4em] text-[#D95A38] font-mono font-bold">
                Architecture // 01
              </div>
              <TechnicalSpecs 
                title="ER Copilot"
                specs={[
                  "Automated legal reasoning via GPT-4o",
                  "Real-time handbook telemetry sync",
                  "Multi-jurisdictional conflict resolution",
                  "Secure document cross-referencing"
                ]}
              />
            </div>
            <h2
              className="text-6xl md:text-[10rem] italic font-light leading-none tracking-tighter"
              style={{ fontFamily: fonts.serif }}
            >
              ER Copilot
            </h2>
            <p className="text-xl md:text-3xl font-light text-[#F0EFEA]/60 max-w-xl leading-relaxed">
              Your autonomous legal counsel. Resolves complex employee 
              relations cases by synthesizing your organization's unique 
              policy logic with active workforce telemetry.
            </p>
            <div className="pt-8 border-t border-white/5">
              <span className="text-[10px] font-mono uppercase tracking-[0.3em] text-[#D95A38]">
                Inference Status: Operational
              </span>
            </div>
          </div>
          <div className="aspect-square max-h-[600px] border border-white/10 rounded-[4rem] bg-white/[0.01] relative overflow-hidden backdrop-blur-3xl shadow-inner group">
            <ERInferenceEngine />
            <div className="absolute inset-0 bg-gradient-to-t from-[#0A0E0C] to-transparent opacity-40" />
          </div>
        </div>
      </motion.div>

      {/* Card 2: Cream (Policy Hub) */}
      <motion.div 
        initial="offscreen"
        whileInView="onscreen"
        viewport={{ once: true, amount: 0.3 }}
        variants={cardVariants}
        className="system-card sticky top-40 min-h-[80vh] w-full flex items-center justify-center p-12 bg-[#F0EFEA] text-[#0A0E0C] rounded-[4rem] origin-top shadow-[0_-20px_100px_rgba(0,0,0,0.6)] z-20"
      >
        <div className="max-w-[1600px] w-full grid grid-cols-1 md:grid-cols-2 gap-32 items-center">
          <div className="aspect-square max-h-[600px] border border-[#0A0E0C]/10 rounded-[4rem] bg-white relative overflow-hidden order-2 md:order-1 shadow-2xl">
            <PolicyMatrixScanner />
          </div>
          <div className="space-y-12 order-1 md:order-2">
            <div className="flex items-center gap-6">
              <div className="text-[10px] uppercase tracking-[0.4em] text-[#D95A38] font-mono font-bold">
                Architecture // 02
              </div>
              <TechnicalSpecs 
                title="Policy Hub"
                specs={[
                  "Immutable acknowledgement logging",
                  "Geospatial policy mapping",
                  "Automated addendum generation",
                  "Native multi-state reconciliation"
                ]}
              />
            </div>
            <h2
              className="text-6xl md:text-[10rem] italic font-light leading-none tracking-tighter"
              style={{ fontFamily: fonts.serif }}
            >
              Policy Hub
            </h2>
            <p className="text-xl md:text-3xl font-light text-[#0A0E0C]/60 max-w-xl leading-relaxed">
              A living, immutable repository for your organization's laws. 
              Track acknowledgements in real-time across biological and 
              geographical boundaries with automated legal refreshes.
            </p>
            <div className="pt-8 border-t border-black/5">
              <span className="text-[10px] font-mono uppercase tracking-[0.3em] text-[#D95A38]">
                Vault Integrity: 100%
              </span>
            </div>
          </div>
        </div>
      </motion.div>

      {/* Card 3: Deep Clay (Incident Logs) */}
      <motion.div 
        initial="offscreen"
        whileInView="onscreen"
        viewport={{ once: true, amount: 0.3 }}
        variants={cardVariants}
        className="system-card sticky top-48 min-h-[80vh] w-full flex items-center justify-center p-12 bg-[#D95A38] text-[#F0EFEA] rounded-[4rem] origin-top shadow-[0_-20px_100px_rgba(0,0,0,0.7)] z-30"
      >
        <div className="max-w-[1600px] w-full grid grid-cols-1 md:grid-cols-2 gap-32 items-center">
          <div className="space-y-12">
            <div className="flex items-center gap-6">
              <div className="text-[10px] uppercase tracking-[0.4em] text-[#0A0E0C] font-mono font-bold">
                Architecture // 03
              </div>
              <TechnicalSpecs 
                title="Incident Logs"
                specs={[
                  "Secure organic dialogue synthesis",
                  "Audit-ready chain of custody",
                  "Real-time safety alerting",
                  "Immutable evidence vaulting"
                ]}
              />
            </div>
            <h2
              className="text-6xl md:text-[10rem] italic font-light leading-none tracking-tighter"
              style={{ fontFamily: fonts.serif }}
            >
              Incident Logs
            </h2>
            <p className="text-xl md:text-3xl font-light text-[#F0EFEA]/90 max-w-xl leading-relaxed">
              Structured workflows for high-stakes safety and security. 
              Audit-ready logs generated automatically from synthesized 
              organic dialogue—eliminating the lag of manual reporting.
            </p>
            <div className="pt-8 border-t border-white/10">
              <button className="px-10 py-5 bg-[#0A0E0C] text-[#F0EFEA] rounded-full text-[10px] font-mono uppercase tracking-[0.3em] hover:bg-[#F0EFEA] hover:text-[#0A0E0C] transition-all duration-500 shadow-2xl hover:scale-105 active:scale-95">
                Initialize Output Sequence
              </button>
            </div>
          </div>
          <div className="aspect-square max-h-[600px] border border-[#0A0E0C]/10 rounded-[4rem] bg-[#0A0E0C]/10 relative shadow-2xl backdrop-blur-3xl overflow-hidden flex flex-col group">
            <div className="flex-1">
              <IncidentAuditRing />
            </div>
            <div className="p-12 border-t border-[#0A0E0C]/10 bg-black/20 flex justify-between items-center">
              <div className="flex gap-3">
                <div className="w-2 h-2 rounded-full bg-white animate-pulse" />
                <div className="w-2 h-2 rounded-full bg-white/20" />
              </div>
              <span className="text-[8px] font-mono uppercase tracking-[0.4em] opacity-40">
                Log Pipeline: Secure
              </span>
            </div>
          </div>
        </div>
      </motion.div>
    </section>
  );
});

SystemProtocols.displayName = "SystemProtocols";

SystemProtocols.displayName = "SystemProtocols";
