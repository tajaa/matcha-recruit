import { lazy, Suspense } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { TelemetryBadge } from "../components/TelemetryBadge";
import { TechnicalSpecs } from "../components/TechnicalSpecs";
import { fonts } from "../constants";

const ParticleSphere = lazy(() => import("../../../components/ParticleSphere"));

export const Hero = () => {
  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.15,
        delayChildren: 0.3,
      },
    },
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 30, filter: "blur(10px)" },
    visible: { 
      opacity: 1, 
      y: 0, 
      filter: "blur(0px)",
      transition: { duration: 1.2, ease: [0.16, 1, 0.3, 1] }
    },
  };

  return (
    <motion.section 
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      className="hero-trigger relative min-h-screen flex flex-col justify-center px-6 md:px-16 lg:px-32 overflow-hidden"
    >
      {/* Background Layer with Iris Scan Effect */}
      <div className="absolute inset-0 z-0 overflow-hidden pointer-events-none">
        <motion.div
          initial={{ scale: 1.2, opacity: 0 }}
          animate={{ scale: 1, opacity: 0.18 }}
          transition={{ duration: 2.5, ease: "easeOut" }}
          className="parallax-bg absolute -inset-[10%] bg-cover bg-center"
          style={{
            backgroundImage: `url('https://images.unsplash.com/photo-1419242902214-272b3f66ee7a?q=80&w=3500&auto=format&fit=crop')`,
          }}
        />
        <div className="absolute inset-0 bg-gradient-to-t from-[#0A0E0C] via-[#0A0E0C]/80 to-transparent" />
        <div className="absolute inset-0 bg-gradient-to-r from-[#0A0E0C] via-transparent to-transparent" />
      </div>

      <div className="relative z-20 w-full max-w-[1600px] mx-auto grid lg:grid-cols-2 gap-12 items-center">
        <div className="flex flex-col items-start relative z-10 pt-20">
          <motion.div variants={itemVariants} className="flex items-center">
            <TelemetryBadge text="Core System v2.4 Online" active />
            <TechnicalSpecs 
              title="Intelligence Engine"
              specs={[
                "Real-time neural rendering via WebGL",
                "Latent data processing (Sub-100ms)",
                "Asynchronous state synchronization",
                "Hardware-accelerated cinematic layer"
              ]}
            />
          </motion.div>
          
          <motion.h1 variants={itemVariants} className="mt-8 leading-[0.85] tracking-tighter mix-blend-lighten">
            <span
              className="reveal-text block text-[4.5rem] md:text-[7.5rem] font-bold uppercase"
              style={{ fontFamily: fonts.sans }}
            >
              Workforce
            </span>
            <span
              className="reveal-text block text-[5.5rem] md:text-[8.5rem] italic font-light text-[#D95A38]"
              style={{ fontFamily: fonts.serif }}
            >
              Intelligence.
            </span>
          </motion.h1>

          <motion.div variants={itemVariants} className="space-y-8 mt-8">
            <p
              className="text-[#F0EFEA]/60 text-lg md:text-2xl font-light leading-relaxed max-w-xl"
              style={{ fontFamily: fonts.sans }}
            >
              The operating system for modern workforce management. <br />
              <span className="text-white font-medium">Stripped of administrative noise.</span> <br />
              Engineered for biological clarity and algorithmic precision.
            </p>
            
            <div className="flex flex-wrap gap-4 pt-4">
              <Link
                to="/register"
                className="px-8 py-4 bg-white text-black text-[10px] font-mono uppercase tracking-[0.3em] hover:bg-[#4ADE80] transition-colors duration-500 rounded-sm"
              >
                Initialize Account
              </Link>
              <button
                className="px-8 py-4 border border-white/10 text-white text-[10px] font-mono uppercase tracking-[0.3em] hover:bg-white/5 transition-colors duration-500 rounded-sm"
              >
                Read Whitepaper
              </button>
            </div>
          </motion.div>
        </div>

        <motion.div
          initial={{ opacity: 0, scale: 0.8, rotateY: 30 }}
          animate={{ opacity: 1, scale: 1, rotateY: 0 }}
          transition={{ duration: 2, ease: [0.16, 1, 0.3, 1], delay: 0.5 }}
          className="relative h-[50vh] lg:h-[80vh] w-full flex items-center justify-center z-0 mt-12 lg:mt-0"
          style={{ transformStyle: "preserve-3d", perspective: "1000px" }}
        >
          <Suspense
            fallback={
              <div className="text-[#4ADE80] font-mono text-[10px] uppercase tracking-widest animate-pulse flex flex-col items-center gap-4">
                <div className="w-8 h-8 border border-[#4ADE80] rounded-full border-t-transparent animate-spin" />
                Booting Neural Sphere...
              </div>
            }
          >
            <div className="absolute inset-0 bg-[#4ADE80]/5 blur-[120px] rounded-full mix-blend-screen pointer-events-none" />
            <ParticleSphere
              className="w-full h-full scale-110 lg:scale-125"
              showCityMarkers
            />
          </Suspense>
        </motion.div>
      </div>
    </motion.section>
  );
};
