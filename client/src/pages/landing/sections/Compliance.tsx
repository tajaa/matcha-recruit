import React from "react";
import { motion } from "framer-motion";
import { MapPin } from "lucide-react";
import { TelemetryBadge } from "../components/TelemetryBadge";
import { TechnicalSpecs } from "../components/TechnicalSpecs";
import { JurisdictionRows } from "../components/JurisdictionRows";
import { fonts } from "../constants";

export const Compliance = () => {
  return (
    <motion.section 
      initial={{ opacity: 0, y: 40 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-100px" }}
      transition={{ duration: 0.8, ease: "easeOut" }}
      className="compliance-trigger py-40 px-6 relative border-t border-white/5 bg-[#0A0E0C]"
    >
      <div className="max-w-[1600px] mx-auto grid lg:grid-cols-2 gap-24 items-center">
        <div className="space-y-12 pr-12">
          <div className="flex items-center">
            <h2
              className="text-4xl md:text-6xl font-bold tracking-tighter leading-[0.9]"
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
                "Multi-tier legal lookup",
                "Automated wage adjustments",
                "Compliance-as-code deployment",
                "Local/State/Federal reconciliation"
              ]}
            />
          </div>
          <p className="text-[#F0EFEA]/60 text-xl font-light leading-relaxed">
            Matcha autonomously monitors labor laws across city, county, and
            state levels—deploying the precise algorithmic rule for every
            employee endpoint natively.
          </p>
        </div>

        <div className="relative z-10 space-y-6">
          <div className="bg-[#0A0E0C] rounded-[2rem] border border-white/10 p-8 shadow-[0_0_50px_rgba(0,0,0,0.5)] overflow-hidden relative">
            <motion.div
              animate={{ top: ["-10%", "110%"] }}
              transition={{ duration: 4, repeat: Infinity, ease: "linear" }}
              className="absolute left-0 right-0 h-[1px] bg-[#4ADE80]/30 shadow-[0_0_20px_#4ADE80] z-30"
            />
            <div className="flex justify-between items-center mb-8 border-b border-white/10 pb-4">
              <div className="flex items-center gap-3">
                <MapPin className="w-4 h-4 text-[#D95A38]" />
                <span className="text-[10px] font-mono uppercase tracking-widest text-[#F0EFEA]/80">
                  Global Matrix
                </span>
              </div>
              <TelemetryBadge text="Syncing" active />
            </div>
            <JurisdictionRows />
          </div>
        </div>
      </div>
    </motion.section>
  );
};
