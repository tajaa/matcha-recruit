import { forwardRef } from "react";
import { ERInferenceEngine } from "../components/ERInferenceEngine";
import { PolicyMatrixScanner } from "../components/PolicyMatrixScanner";
import { IncidentAuditRing } from "../components/IncidentAuditRing";
import { TechnicalSpecs } from "../components/TechnicalSpecs";
import { fonts } from "../constants";

export const SystemProtocols = forwardRef<HTMLDivElement>((_, ref) => {
  return (
    <section ref={ref} className="system-trigger relative mt-40">
      {/* Card 1: Obsidian (ER Copilot) */}
      <div className="system-card sticky top-0 h-screen w-full flex items-center justify-center p-6 bg-[#0A0E0C] border-t border-white/10 origin-top z-10 will-change-transform">
        <div className="max-w-[1600px] w-full grid grid-cols-1 md:grid-cols-2 gap-24 items-center">
          <div className="space-y-8">
            <div className="flex items-center gap-4 text-[10px] uppercase tracking-[0.3em] text-[#D95A38] font-mono">
              Architecture // 01
              <TechnicalSpecs 
                title="ER Copilot"
                specs={[
                  "Automated legal reasoning",
                  "Handbook telemetry sync",
                  "Document cross-referencing",
                  "Conflict resolution engine"
                ]}
              />
            </div>
            <h2
              className="text-5xl md:text-8xl italic font-light"
              style={{ fontFamily: fonts.serif }}
            >
              ER Copilot
            </h2>
            <p className="text-xl font-light text-[#F0EFEA]/60 max-w-md">
              Your automated legal counsel. Resolves complex employee
              relations cases using your specific policy handbook and active
              telemetry.
            </p>
          </div>
          {/* Dynamic Interactive Artifact */}
          <div className="aspect-square max-h-[500px] border border-white/5 rounded-[3rem] bg-white/[0.02] relative overflow-hidden backdrop-blur-md">
            <ERInferenceEngine />
          </div>
        </div>
      </div>

      {/* Card 2: Cream (Policy Hub) */}
      <div className="system-card sticky top-0 h-screen w-full flex items-center justify-center p-6 bg-[#F0EFEA] text-[#0A0E0C] origin-top shadow-[0_-20px_50px_rgba(0,0,0,0.5)] z-20 will-change-transform">
        <div className="max-w-[1600px] w-full grid grid-cols-1 md:grid-cols-2 gap-24 items-center">
          {/* Dynamic Interactive Artifact */}
          <div className="aspect-square max-h-[500px] border border-[#0A0E0C]/10 rounded-[3rem] bg-white relative overflow-hidden order-2 md:order-1 shadow-inner">
            <PolicyMatrixScanner />
          </div>
          <div className="space-y-8 order-1 md:order-2">
            <div className="flex items-center gap-4 text-[10px] uppercase tracking-[0.3em] text-[#D95A38] font-mono">
              Architecture // 02
              <TechnicalSpecs 
                title="Policy Hub"
                specs={[
                  "Distributed ledger logging",
                  "Multi-tenant data isolation",
                  "Real-time acknowledgement tracking",
                  "Geospatial policy mapping"
                ]}
              />
            </div>
            <h2
              className="text-5xl md:text-8xl italic font-light"
              style={{ fontFamily: fonts.serif }}
            >
              Policy Hub
            </h2>
            <p className="text-xl font-light text-[#0A0E0C]/60 max-w-md">
              A living repository for your organization's laws. Track
              acknowledgements in real-time across biological and geographical
              limits.
            </p>
          </div>
        </div>
      </div>

      {/* Card 3: Deep Clay (Incident Logs) */}
      <div className="system-card sticky top-0 h-screen w-full flex items-center justify-center p-6 bg-[#D95A38] text-[#F0EFEA] origin-top shadow-[0_-20px_50px_rgba(0,0,0,0.5)] z-30 will-change-transform">
        <div className="max-w-[1600px] w-full grid grid-cols-1 md:grid-cols-2 gap-24 items-center">
          <div className="space-y-8">
            <div className="flex items-center gap-4 text-[10px] uppercase tracking-[0.3em] text-[#0A0E0C] font-mono font-bold">
              Architecture // 03
              <TechnicalSpecs 
                title="Incident Logs"
                specs={[
                  "Synthesized organic logging",
                  "Immutable audit trails",
                  "Secure evidence vault",
                  "Real-time safety alerting"
                ]}
              />
            </div>
            <h2
              className="text-5xl md:text-8xl italic font-light"
              style={{ fontFamily: fonts.serif }}
            >
              Incident Logs
            </h2>
            <p className="text-xl font-light text-[#F0EFEA]/90 max-w-md">
              Structured workflows for safety and security. Audit-ready logs
              generated automatically from synthesized organic dialogue.
            </p>
          </div>
          {/* Dynamic Interactive Artifact */}
          <div className="aspect-square max-h-[500px] border border-[#0A0E0C]/10 rounded-[3rem] bg-[#0A0E0C]/10 relative shadow-2xl backdrop-blur-md overflow-hidden flex flex-col">
            <div className="flex-1">
              <IncidentAuditRing />
            </div>
            <div className="p-8 border-t border-[#0A0E0C]/10">
              <button className="w-full py-4 bg-[#0A0E0C] text-[#F0EFEA] rounded-full text-[10px] font-mono uppercase tracking-[0.2em] hover:bg-[#F0EFEA] hover:text-[#0A0E0C] transition-colors shadow-lg">
                Initialize Output
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
});

SystemProtocols.displayName = "SystemProtocols";
