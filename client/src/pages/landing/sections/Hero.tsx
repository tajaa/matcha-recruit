import { lazy, Suspense } from "react";
import { Link } from "react-router-dom";
import { motion, type Variants } from "framer-motion";
import { TelemetryBadge } from "../components/TelemetryBadge";
import { TechnicalSpecs } from "../components/TechnicalSpecs";
import { fonts } from "../constants";

const ParticleSphere = lazy(() => import("../../../components/ParticleSphere"));

export const Hero = () => {
  const containerVariants: Variants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1,
        delayChildren: 0.2,
      },
    },
  };

  const itemVariants: Variants = {
    hidden: { opacity: 0, y: 20, filter: "blur(8px)" },
    visible: { 
      opacity: 1, 
      y: 0, 
      filter: "blur(0px)",
      transition: { duration: 1, ease: [0.16, 1, 0.3, 1] }
    },
  };

  return (
    <motion.section 
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      className="hero-trigger relative min-h-[90vh] flex flex-col justify-center px-6 md:px-16 lg:px-32 overflow-hidden"
    >
      {/* Atmosphere Layer - Minimalist Grayscale */}
      <div className="absolute inset-0 z-0 overflow-hidden pointer-events-none">
        <div className="absolute inset-0 bg-[#0A0E0C]" />
        {/* Subtle radial depth instead of bright green */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[1200px] h-[800px] bg-white/[0.02] blur-[150px] rounded-full mix-blend-screen" />
        <div className="absolute top-0 left-0 w-full h-full opacity-[0.03] pointer-events-none bg-[url('https://www.transparenttextures.com/patterns/asfalt-light.png')]" />
      </div>

      <div className="relative z-20 w-full max-w-[1400px] mx-auto grid lg:grid-cols-[1fr_0.8fr] gap-12 items-center">
        <div className="flex flex-col items-start relative z-10 py-20">
          <motion.div variants={itemVariants} className="flex items-center gap-4">
            <TelemetryBadge text="System Core // Offline Mode" active={false} />
            <div className="h-px w-8 bg-white/5" />
            <TechnicalSpecs 
              title="Architecture"
              specs={[
                "Sub-100ms Latent Synthesis",
                "Neural State Machine v4.2",
                "Hardware-Accelerated Rasterization",
                "AES-256 Protocol Isolation"
              ]}
            />
          </motion.div>
          
          <motion.h1 variants={itemVariants} className="mt-10 leading-[0.9] tracking-[-0.04em] mix-blend-lighten max-w-2xl">
            <span
              className="block text-[3.5rem] md:text-[5.5rem] lg:text-[7.5rem] font-bold uppercase text-white"
              style={{ fontFamily: fonts.display, letterSpacing: '0.05em' }}
            >
              Workforce
            </span>
            <span
              className="block text-[4rem] md:text-[6.5rem] lg:text-[8.5rem] italic font-light text-zinc-500"
              style={{ fontFamily: fonts.serif }}
            >
              Intelligence.
            </span>
          </motion.h1>

          <motion.div variants={itemVariants} className="space-y-10 mt-10">
            <p
              className="text-zinc-500 text-base md:text-lg lg:text-xl font-light leading-relaxed max-w-lg"
              style={{ fontFamily: fonts.sans }}
            >
              The unified operating system for modern workforce architecture. 
              <span className="text-zinc-300 font-medium"> Stripped of noise.</span> Optimized for 
              biological clarity and algorithmic precision.
            </p>
            
            <div className="flex flex-wrap gap-6 pt-2">
              <Link
                to="/register"
                className="group relative px-10 py-4 bg-white text-black text-[10px] font-mono uppercase tracking-[0.3em] font-bold overflow-hidden"
              >
                <span className="relative z-10">Initialize Account</span>
                <motion.div 
                  className="absolute inset-0 bg-zinc-200 translate-y-full group-hover:translate-y-0 transition-transform duration-500 ease-[0.16,1,0.3,1]"
                />
              </Link>
              <button
                className="px-10 py-4 border border-white/10 text-white/40 text-[10px] font-mono uppercase tracking-[0.3em] hover:text-white hover:border-white/30 transition-all duration-500 font-bold"
              >
                Read Whitepaper
              </button>
            </div>
          </motion.div>
        </div>

        <motion.div
          initial={{ opacity: 0, scale: 0.9, x: 20 }}
          animate={{ opacity: 1, scale: 1, x: 0 }}
          transition={{ duration: 1.5, ease: [0.16, 1, 0.3, 1], delay: 0.4 }}
          className="relative h-[40vh] lg:h-[70vh] w-full flex items-center justify-center z-0 group"
        >
          <Suspense
            fallback={
              <div className="text-white/20 font-mono text-[8px] uppercase tracking-[0.4em] animate-pulse">
                Booting Neural Sphere...
              </div>
            }
          >
            <div className="absolute inset-0 bg-white/[0.03] blur-[100px] rounded-full mix-blend-screen pointer-events-none group-hover:bg-white/[0.05] transition-colors duration-1000" />
            <ParticleSphere
              className="w-full h-full scale-100 lg:scale-110 opacity-80"
              showCityMarkers
            />
          </Suspense>
        </motion.div>
      </div>
    </motion.section>
  );
};
