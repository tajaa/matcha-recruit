import { forwardRef } from "react";
import { m, type Variants } from "framer-motion";
import { Scale, BookOpen, ShieldAlert } from "lucide-react";
import { TelemetryBadge } from "../components/TelemetryBadge";
import { TechnicalSpecs } from "../components/TechnicalSpecs";
import { useInViewport } from "../hooks/useInViewport";
import { fonts, ER_INFERENCE_WIDTHS } from "../constants";

export const ERCopilot = forwardRef<HTMLDivElement>((_, ref) => {
  const { ref: sectionRef, isVisible } = useInViewport();
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
      className="er-copilot-trigger py-64 px-6 md:px-16 lg:px-32 relative bg-[#0A0E0C] overflow-hidden"
    >
      <div ref={sectionRef} />
      {/* Background Depth */}
      <div className="absolute inset-0 z-0 pointer-events-none opacity-[0.03]">
        <div className="absolute top-0 left-0 w-full h-full bg-[url('/textures/asfalt-light.png')]" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] rounded-full mix-blend-screen" style={{ background: "radial-gradient(circle, white 0%, transparent 70%)" }} />
      </div>

      <div className="max-w-[1600px] mx-auto grid lg:grid-cols-2 gap-32 items-center relative z-10">
        <m.div 
          initial={{ opacity: 0, scale: 0.9, x: -50 }}
          whileInView={{ opacity: 1, scale: 1, x: 0 }}
          transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
          className="order-2 lg:order-1 relative"
        >
          {/* Analysis Matrix Visual */}
          <div className="relative aspect-square max-w-lg mx-auto bg-black border border-white/10 flex flex-col justify-between p-12 overflow-hidden shadow-[0_0_80px_rgba(255,255,255,0.02)] group">
            <div className="absolute top-0 right-0 w-full h-full bg-[linear-gradient(45deg,transparent_25%,rgba(255,255,255,0.02)_50%,transparent_75%)] bg-[length:250%_250%,100%_100%] animate-[gradient_8s_linear_infinite]" />
            
            <div className="flex justify-between items-start z-10">
              <div className="flex flex-col gap-2">
                <span className="flex items-center gap-3 text-[10px] text-white uppercase tracking-[0.3em] font-bold">
                  <Scale size={14} className="text-zinc-500" /> Precedent Engine
                </span>
                <span className="text-[8px] text-zinc-500 uppercase tracking-widest">
                  Status: Evaluating
                </span>
              </div>
              <div className="px-3 py-1 bg-white/5 border border-white/10 text-[8px] font-mono text-white/50 uppercase tracking-widest">
                Confidential
              </div>
            </div>

            <div className="flex-1 flex flex-col justify-center gap-6 my-12 z-10 relative">
              <div className="absolute -left-12 top-1/2 -translate-y-1/2 w-[1px] h-[150%] bg-gradient-to-b from-transparent via-white/20 to-transparent" />
              
              {[
                { label: "Policy Cross-Ref", match: "94%" },
                { label: "Case Similarity", match: "82%" },
                { label: "Legal Exposure", match: "Low" }
              ].map((item, i) => (
                <div key={i} className="flex flex-col gap-2 group/item">
                  <div className="flex justify-between text-[10px] font-mono uppercase tracking-widest text-zinc-500 group-hover/item:text-white transition-colors">
                    <span>{item.label}</span>
                    <span className="text-white">{item.match}</span>
                  </div>
                  <div className="h-[2px] w-full bg-white/5 relative overflow-hidden">
                    <m.div 
                      initial={{ width: 0 }}
                      whileInView={{ width: item.match === "Low" ? "15%" : item.match }}
                      transition={{ duration: 1.5, delay: i * 0.2, ease: "easeOut" }}
                      className="absolute top-0 left-0 h-full bg-white/40"
                    />
                  </div>
                </div>
              ))}
            </div>
            
            <div className="w-full font-mono border-t border-white/10 pt-8 z-10">
              <div className="flex justify-between items-end mb-4">
                <span className="text-[10px] text-zinc-400 uppercase tracking-[0.2em]">
                  Inference Matrix
                </span>
                <div className="flex gap-1 items-end h-6">
                  {ER_INFERENCE_WIDTHS.map((h, i) => (
                    <div
                      key={i}
                      className="w-[2px] bg-white/30"
                      style={{
                        height: `${h * 100}%`,
                        animation: isVisible ? `landing-bar-bounce ${1.5 + i * 0.2}s ease-in-out infinite` : "none",
                        transformOrigin: "bottom",
                      }}
                    />
                  ))}
                </div>
              </div>
            </div>
          </div>
        </m.div>

        <div className="order-1 lg:order-2 space-y-12">
          <m.div variants={featureVariants} className="flex items-center gap-4">
            <TelemetryBadge text="Risk Assessment" active={false} />
            <TechnicalSpecs 
              title="Relations Engine"
              specs={[
                "Historical Precedent Search",
                "Automated Policy Parsing",
                "Sentiment & Intent Analysis",
                "Actionable Next Steps"
              ]}
            />
          </m.div>

          <m.h2
            variants={featureVariants}
            className="text-4xl md:text-6xl font-bold tracking-tighter leading-[0.85]"
            style={{ fontFamily: fonts.display, letterSpacing: '0.05em' }}
          >
            ER <br />
            <span
              className="italic text-zinc-500 font-light lowercase"
              style={{ fontFamily: fonts.serif, letterSpacing: 'normal' }}
            >
              Copilot.
            </span>
          </m.h2>

          <m.p 
            variants={featureVariants}
            className="text-zinc-500 text-xl md:text-2xl font-light leading-relaxed max-w-xl"
            style={{ fontFamily: fonts.sans }}
          >
            Your intelligent guide for employee relations. Make confident, evidence-based decisions with similarity flags and precedent reminders.
          </m.p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-12 pt-8 border-t border-white/5">
            <m.div variants={featureVariants} className="space-y-4 group">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-white/5 text-white group-hover:bg-white group-hover:text-black transition-colors">
                  <BookOpen size={20} />
                </div>
                <h4 className="font-bold text-white uppercase tracking-[0.2em] text-xs font-mono">
                  Policy Parsing
                </h4>
              </div>
              <p className="text-zinc-500 text-sm leading-relaxed border-l border-white/10 pl-4 font-mono">
                Instantly cross-references case details with your active company handbook.
              </p>
            </m.div>

            <m.div variants={featureVariants} className="space-y-4 group">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-white/5 text-white group-hover:bg-white group-hover:text-black transition-colors">
                  <ShieldAlert size={20} />
                </div>
                <h4 className="font-bold text-white uppercase tracking-[0.2em] text-xs font-mono">
                  Risk Flags
                </h4>
              </div>
              <p className="text-zinc-500 text-sm leading-relaxed border-l border-white/10 pl-4 font-mono">
                Highlights potential liabilities based on historical precedent and labor law.
              </p>
            </m.div>
          </div>
        </div>
      </div>
    </m.section>
  );
});

ERCopilot.displayName = "ERCopilot";