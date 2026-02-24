import { motion, type Variants } from "framer-motion";
import { MapPin, Shield, Zap, Search } from "lucide-react";
import { TelemetryBadge } from "../components/TelemetryBadge";
import { TechnicalSpecs } from "../components/TechnicalSpecs";
import { JurisdictionRows } from "../components/JurisdictionRows";
import { fonts } from "../constants";

export const Compliance = () => {
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
    <motion.section 
      variants={containerVariants}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: "-100px" }}
      className="compliance-trigger py-64 px-6 md:px-16 lg:px-32 relative border-t border-white/5 bg-[#0A0E0C]"
    >
      <div className="max-w-[1600px] mx-auto grid lg:grid-cols-2 gap-32 items-center">
        <div className="space-y-16 pr-12">
          <motion.div variants={textVariants} className="space-y-6">
            <div className="flex items-center gap-4">
              <h2
                className="text-5xl md:text-7xl font-bold tracking-tighter leading-[0.9]"
                style={{ fontFamily: fonts.sans }}
              >
                HIERARCHICAL <br />
                <span
                  className="italic text-[#4ADE80] font-light"
                  style={{ fontFamily: fonts.serif }}
                >
                  Jurisdiction Mapping.
                </span>
              </h2>
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
            <p className="text-[#F0EFEA]/60 text-xl md:text-2xl font-light leading-relaxed max-w-2xl">
              Eliminate the manual burden of labor law research. Matcha autonomously 
              monitors 10,000+ legislative nodes—deploying the precise algorithmic 
              rule for every employee endpoint natively.
            </p>
          </motion.div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-12">
            <motion.div variants={textVariants} className="space-y-4">
              <div className="w-10 h-10 rounded-full bg-[#4ADE80]/10 flex items-center justify-center">
                <Zap size={18} className="text-[#4ADE80]" />
              </div>
              <h4 className="text-sm font-bold uppercase tracking-widest font-mono text-white">
                Live Adaptation
              </h4>
              <p className="text-xs text-[#F0EFEA]/50 leading-relaxed font-medium">
                When a city updates its minimum wage or predictive scheduling laws, 
                your entire workforce infrastructure adapts in the same pay period.
              </p>
            </motion.div>
            <motion.div variants={textVariants} className="space-y-4">
              <div className="w-10 h-10 rounded-full bg-[#D95A38]/10 flex items-center justify-center">
                <Shield size={18} className="text-[#D95A38]" />
              </div>
              <h4 className="text-sm font-bold uppercase tracking-widest font-mono text-white">
                Safe Harbor Sync
              </h4>
              <p className="text-xs text-[#F0EFEA]/50 leading-relaxed font-medium">
                Every policy is verified against the highest standard of employee 
                protection to minimize litigation risk across state lines.
              </p>
            </motion.div>
          </div>
        </div>

        <motion.div 
          initial={{ opacity: 0, scale: 0.9, rotateY: -15 }}
          whileInView={{ opacity: 1, scale: 1, rotateY: 0 }}
          transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
          viewport={{ once: true }}
          className="relative z-10 space-y-6"
        >
          <div className="bg-[#0A0E0C] rounded-[3rem] border border-white/10 p-12 shadow-[0_0_100px_rgba(0,0,0,0.8)] overflow-hidden relative group">
            <motion.div
              animate={{ top: ["-10%", "110%"] }}
              transition={{ duration: 4, repeat: Infinity, ease: "linear" }}
              className="absolute left-0 right-0 h-[1px] bg-[#4ADE80]/40 shadow-[0_0_30px_#4ADE80] z-30"
            />
            
            <div className="flex justify-between items-center mb-12 border-b border-white/10 pb-6">
              <div className="flex items-center gap-4">
                <div className="p-2 bg-[#D95A38]/20 rounded-lg">
                  <MapPin className="w-5 h-5 text-[#D95A38]" />
                </div>
                <div>
                  <span className="block text-[10px] font-mono uppercase tracking-widest text-white font-bold">
                    Global Matrix
                  </span>
                  <span className="text-[8px] font-mono text-[#F0EFEA]/40 uppercase tracking-[0.2em]">
                    Algorithmic Enforcement Active
                  </span>
                </div>
              </div>
              <TelemetryBadge text="Syncing Node" active />
            </div>

            <JurisdictionRows />

            <div className="mt-12 pt-8 border-t border-white/5 flex justify-between items-center">
              <div className="flex gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-[#4ADE80] animate-pulse" />
                <div className="w-1.5 h-1.5 rounded-full bg-[#4ADE80]/30" />
                <div className="w-1.5 h-1.5 rounded-full bg-[#4ADE80]/10" />
              </div>
              <span className="text-[8px] font-mono uppercase tracking-[0.3em] text-[#F0EFEA]/30">
                Latent Nodes: 12,402
              </span>
            </div>
          </div>
          
          {/* Decorative Technical Overlay */}
          <div className="absolute -bottom-12 -right-12 w-64 h-64 border border-white/5 rounded-full flex items-center justify-center opacity-20 pointer-events-none group-hover:opacity-40 transition-opacity">
            <Search size={120} className="text-white/10 rotate-12" />
          </div>
        </motion.div>
      </div>
    </motion.section>
  );
};
