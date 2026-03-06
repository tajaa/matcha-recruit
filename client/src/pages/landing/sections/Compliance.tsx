import { m, type Variants } from "framer-motion";
import { MapPin, Shield, Zap, Globe, Users } from "lucide-react";
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

        </m.div>
      </div>
    </m.section>
  );
};
