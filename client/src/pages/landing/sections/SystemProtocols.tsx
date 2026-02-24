import { forwardRef } from "react";
import { motion, type Variants } from "framer-motion";
import { ERInferenceEngine } from "../components/ERInferenceEngine";
import { PolicyMatrixScanner } from "../components/PolicyMatrixScanner";
import { IncidentAuditRing } from "../components/IncidentAuditRing";
import { TechnicalSpecs } from "../components/TechnicalSpecs";
import { fonts } from "../constants";

export const SystemProtocols = forwardRef<HTMLDivElement>((_, ref) => {
  const cardVariants: Variants = {
    offscreen: { y: 60, opacity: 0, scale: 0.98 },
    onscreen: { 
      y: 0, 
      opacity: 1, 
      scale: 1,
      transition: { 
        type: "spring", 
        stiffness: 100,
        damping: 20,
        duration: 1 
      } 
    }
  };

  return (
    <section ref={ref} className="system-trigger relative mt-32 space-y-24 px-6 md:px-16 lg:px-32 pb-64">
      {/* Card 1: Obsidian (ER Copilot) */}
      <motion.div 
        initial="offscreen"
        whileInView="onscreen"
        viewport={{ once: true, amount: 0.2 }}
        variants={cardVariants}
        className="system-card sticky top-24 min-h-[70vh] w-full flex items-center justify-center p-8 md:p-16 bg-[#0A0E0C] border border-white/10 rounded-[3rem] origin-top z-10 shadow-2xl"
      >
        <div className="max-w-[1400px] w-full grid grid-cols-1 md:grid-cols-[1fr_0.8fr] gap-16 md:gap-24 items-center">
          <div className="space-y-10">
            <div className="flex items-center gap-6">
              <div className="text-[9px] uppercase tracking-[0.4em] text-[#D95A38] font-mono font-bold">
                Architecture // 01
              </div>
              <TechnicalSpecs 
                title="ER Copilot"
                specs={[
                  "Neural Synthesis Engine v4",
                  "Handbook Telemetry Bridge",
                  "Multi-Jurisdictional Resolver",
                  "Secure Audit Vaulting"
                ]}
              />
            </div>
            <h2
              className="text-5xl md:text-7xl lg:text-8xl italic font-light leading-none tracking-tighter"
              style={{ fontFamily: fonts.serif }}
            >
              ER Copilot
            </h2>
            <p className="text-base md:text-lg lg:text-xl font-light text-[#F0EFEA]/50 max-w-lg leading-relaxed">
              Your autonomous legal counsel. Resolves complex employee 
              relations by synthesizing unique policy logic with 
              real-time workforce telemetry.
            </p>
            <div className="pt-6 border-t border-white/5 flex items-center gap-3">
              <div className="w-1 h-1 rounded-full bg-[#D95A38] animate-pulse" />
              <span className="text-[9px] font-mono uppercase tracking-[0.3em] text-[#D95A38]/80 font-bold">
                Inference Node: Active
              </span>
            </div>
          </div>
          <div className="aspect-square w-full max-w-[500px] mx-auto border border-white/10 rounded-[3rem] bg-white/[0.01] relative overflow-hidden backdrop-blur-3xl shadow-inner group">
            <ERInferenceEngine />
            <div className="absolute inset-0 bg-gradient-to-t from-[#0A0E0C] to-transparent opacity-40" />
          </div>
        </div>
      </motion.div>

      {/* Card 2: Cream (Policy Hub) */}
      <motion.div 
        initial="offscreen"
        whileInView="onscreen"
        viewport={{ once: true, amount: 0.2 }}
        variants={cardVariants}
        className="system-card sticky top-32 min-h-[70vh] w-full flex items-center justify-center p-8 md:p-16 bg-[#F0EFEA] text-[#0A0E0C] rounded-[3rem] origin-top shadow-[0_-20px_80px_rgba(0,0,0,0.4)] z-20"
      >
        <div className="max-w-[1400px] w-full grid grid-cols-1 md:grid-cols-[0.8fr_1fr] gap-16 md:gap-24 items-center">
          <div className="aspect-square w-full max-w-[500px] mx-auto border border-[#0A0E0C]/10 rounded-[3rem] bg-white relative overflow-hidden order-2 md:order-1 shadow-2xl">
            <PolicyMatrixScanner />
          </div>
          <div className="space-y-10 order-1 md:order-2">
            <div className="flex items-center gap-6">
              <div className="text-[9px] uppercase tracking-[0.4em] text-[#D95A38] font-mono font-bold">
                Architecture // 02
              </div>
              <TechnicalSpecs 
                title="Policy Hub"
                specs={[
                  "Immutable Ledger Logging",
                  "Geospatial Law Mapping",
                  "Automated Addendum Streams",
                  "Native Multi-State Sync"
                ]}
              />
            </div>
            <h2
              className="text-5xl md:text-7xl lg:text-8xl italic font-light leading-none tracking-tighter"
              style={{ fontFamily: fonts.serif }}
            >
              Policy Hub
            </h2>
            <p className="text-base md:text-lg lg:text-xl font-light text-[#0A0E0C]/50 max-w-lg leading-relaxed">
              An immutable repository for your organization's laws. 
              Track acknowledgements in real-time across biological 
              and geographical boundaries.
            </p>
            <div className="pt-6 border-t border-black/5 flex items-center gap-3">
              <div className="w-1 h-1 rounded-full bg-[#0A0E0C] animate-pulse" />
              <span className="text-[9px] font-mono uppercase tracking-[0.3em] text-[#0A0E0C]/60 font-bold">
                Vault Integrity: Nominal
              </span>
            </div>
          </div>
        </div>
      </motion.div>

      {/* Card 3: Deep Clay (Incident Logs) */}
      <motion.div 
        initial="offscreen"
        whileInView="onscreen"
        viewport={{ once: true, amount: 0.2 }}
        variants={cardVariants}
        className="system-card sticky top-40 min-h-[70vh] w-full flex items-center justify-center p-8 md:p-16 bg-[#D95A38] text-[#F0EFEA] rounded-[3rem] origin-top shadow-[0_-20px_80px_rgba(0,0,0,0.5)] z-30"
      >
        <div className="max-w-[1400px] w-full grid grid-cols-1 md:grid-cols-[1fr_0.8fr] gap-16 md:gap-24 items-center">
          <div className="space-y-10">
            <div className="flex items-center gap-6">
              <div className="text-[9px] uppercase tracking-[0.4em] text-[#0A0E0C] font-mono font-bold">
                Architecture // 03
              </div>
              <TechnicalSpecs 
                title="Incident Logs"
                specs={[
                  "Organic Dialogue Synthesis",
                  "Chain-of-Custody Validation",
                  "Real-time Hazard Alerting",
                  "Secure Evidence Vaulting"
                ]}
              />
            </div>
            <h2
              className="text-5xl md:text-7xl lg:text-8xl italic font-light leading-none tracking-tighter"
              style={{ fontFamily: fonts.serif }}
            >
              Incident Logs
            </h2>
            <p className="text-base md:text-lg lg:text-xl font-light text-[#F0EFEA]/80 max-w-lg leading-relaxed">
              Structured workflows for high-stakes security. 
              Audit-ready logs generated from synthesized 
              organic dialogue—eliminating manual lag.
            </p>
            <div className="pt-6">
              <button className="px-10 py-4 bg-[#0A0E0C] text-[#F0EFEA] rounded-full text-[9px] font-mono uppercase tracking-[0.3em] font-bold hover:bg-[#F0EFEA] hover:text-[#0A0E0C] transition-all duration-500 shadow-2xl">
                Initialize Output
              </button>
            </div>
          </div>
          <div className="aspect-square w-full max-w-[500px] mx-auto border border-[#0A0E0C]/10 rounded-[3rem] bg-[#0A0E0C]/10 relative shadow-2xl backdrop-blur-3xl overflow-hidden flex flex-col group">
            <div className="flex-1">
              <IncidentAuditRing />
            </div>
            <div className="p-8 border-t border-[#0A0E0C]/10 bg-black/10 flex justify-between items-center">
              <div className="flex gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
                <div className="w-1.5 h-1.5 rounded-full bg-white/20" />
              </div>
              <span className="text-[7px] font-mono uppercase tracking-[0.4em] opacity-40">
                Encrypted Pipeline: Active
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

SystemProtocols.displayName = "SystemProtocols";
