import { lazy, Suspense, useState, useEffect, useRef } from "react";
import { m, type Variants } from "framer-motion";
import { TelemetryBadge } from "../components/TelemetryBadge";
import { TechnicalSpecs } from "../components/TechnicalSpecs";
import { AsciiHalftone } from "../components/AsciiHalftone";
import { useInViewport } from "../hooks/useInViewport";
import { fonts } from "../constants";

const ParticleSphere = lazy(() => import("../../../components/ParticleSphere"));

const MATRIX_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZｦｧｨｩｪｫｬｭｮｯｰｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ0123456789!@#$%&';

function GlitchText({ text, className, style }: { text: string; className?: string; style?: React.CSSProperties }) {
  const [chars, setChars] = useState<string[]>(() =>
    text.split('').map(c => (c === ' ' || c === '.') ? c : MATRIX_CHARS[Math.floor(Math.random() * MATRIX_CHARS.length)])
  );
  const [isGlitching, setIsGlitching] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Decode left-to-right on mount
  useEffect(() => {
    const textArr = text.split('');
    let revealProgress = 0;
    const decode = setInterval(() => {
      setChars(prev =>
        prev.map((_, i) => {
          if (textArr[i] === ' ' || textArr[i] === '.') return textArr[i];
          if (i < revealProgress) return textArr[i];
          return MATRIX_CHARS[Math.floor(Math.random() * MATRIX_CHARS.length)];
        })
      );
      revealProgress += 0.4;
      if (revealProgress >= textArr.length) {
        clearInterval(decode);
        setChars(textArr);
      }
    }, 45);
    return () => clearInterval(decode);
  }, [text]);

  // Periodic glitch — paused when off-screen
  const { ref: glitchRef, isVisible: glitchVisible } = useInViewport();
  const glitchVisibleRef = useRef(glitchVisible);
  glitchVisibleRef.current = glitchVisible;

  useEffect(() => {
    const scheduleGlitch = () => {
      timeoutRef.current = setTimeout(() => {
        if (!glitchVisibleRef.current) { scheduleGlitch(); return; }
        setIsGlitching(true);
        let ticks = 0;
        const maxTicks = 7 + Math.floor(Math.random() * 8);
        intervalRef.current = setInterval(() => {
          setChars(
            text.split('').map(c => {
              if (c === ' ' || c === '.') return c;
              return Math.random() > 0.35 ? c : MATRIX_CHARS[Math.floor(Math.random() * MATRIX_CHARS.length)];
            })
          );
          ticks++;
          if (ticks >= maxTicks) {
            clearInterval(intervalRef.current!);
            setChars(text.split(''));
            setIsGlitching(false);
            scheduleGlitch();
          }
        }, 55);
      }, 2800 + Math.random() * 4000);
    };
    scheduleGlitch();
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [text]);

  return (
    <span
      ref={glitchRef}
      className={className}
      style={{
        ...style,
        textShadow: isGlitching ? '3px 0 #9ca3af, -3px 0 #d1d5db' : 'none',
        color: isGlitching ? '#6b7280' : undefined,
        transition: 'color 0.05s, text-shadow 0.05s',
      }}
    >
      {chars.join('')}
    </span>
  );
}

interface HeroProps {
  onContactClick?: () => void;
}

export const Hero = ({ onContactClick }: HeroProps) => {
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
    <m.section
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      className="hero-trigger relative min-h-[90vh] flex flex-col justify-center px-6 md:px-16 lg:px-32 overflow-hidden"
    >
      {/* Atmosphere Layer - Minimalist Light Grayscale */}
      <div className="absolute inset-0 z-0 overflow-hidden pointer-events-none">
        <div className="absolute inset-0 bg-[#f4f4f5]" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[1200px] h-[800px] rounded-full mix-blend-multiply" style={{ background: "radial-gradient(circle, rgba(0,0,0,0.03) 0%, transparent 70%)" }} />
        <div className="absolute top-0 left-0 w-full h-full opacity-[0.06] pointer-events-none bg-[url('/textures/asfalt-light.png')]" />
      </div>

      <AsciiHalftone />

      <div className="relative z-10 w-full max-w-[1600px] mx-auto grid lg:grid-cols-[1fr_0.8fr] gap-12 items-center">
        <div className="flex flex-col items-start relative z-10 py-20">
          <m.div variants={itemVariants} className="flex items-center gap-4">
            <TelemetryBadge text="System Core // Offline Mode" active={false} />
            <div className="h-px w-8 bg-black/10" />
            <TechnicalSpecs 
              title="Architecture"
              specs={[
                "Sub-100ms Latent Synthesis",
                "Neural State Machine v4.2",
                "Hardware-Accelerated Rasterization",
                "AES-256 Protocol Isolation"
              ]}
            />
          </m.div>
          
          <div className="mt-10 rounded-xl backdrop-blur-sm px-6 py-5 -mx-6 w-fit shadow-[0_8px_32px_rgba(0,0,0,0.08)]">
            <m.h1 variants={itemVariants} className="leading-[0.9] tracking-[-0.04em] mix-blend-darken max-w-2xl">
              <span
                className="block text-[1.875rem] md:text-[3rem] lg:text-[3.75rem] font-bold uppercase text-zinc-800"
                style={{ fontFamily: fonts.display, letterSpacing: '0.05em' }}
              >
                Workforce
              </span>
              <GlitchText
                text="Intelligence."
                className="block text-[2.25rem] md:text-[3.75rem] lg:text-[4.5rem] italic font-light text-zinc-700"
                style={{
                  fontFamily: fonts.serif,
                }}
              />
            </m.h1>

            <m.div variants={itemVariants} className="space-y-10 mt-10">
              <p
                className="text-zinc-900 text-lg md:text-xl lg:text-2xl font-semibold leading-relaxed w-fit whitespace-nowrap"
                style={{ fontFamily: fonts.sans }}
              >
                Increase your <span className="text-amber-700">signal to noise ratio</span>.
              </p>
            
            <div className="flex flex-wrap gap-6 pt-2">
              <button
                onClick={onContactClick}
                className="group relative px-10 py-4 bg-zinc-900 text-white text-[10px] font-mono uppercase tracking-[0.3em] font-bold overflow-hidden border border-zinc-900"
              >
                <span className="relative z-10 group-hover:text-black transition-colors duration-500">Initialize Account</span>
                <m.div 
                  className="absolute inset-0 bg-white translate-y-full group-hover:translate-y-0 transition-transform duration-500 ease-[0.16,1,0.3,1]"
                />
              </button>
            </div>
          </m.div>
          </div>
        </div>

        <m.div
          initial={{ opacity: 0, scale: 0.9, x: 20 }}
          animate={{ opacity: 1, scale: 1, x: 0 }}
          transition={{ duration: 1.5, ease: [0.16, 1, 0.3, 1], delay: 0.4 }}
          className="relative h-[38vh] lg:h-[66vh] w-full flex items-center justify-center z-0 group overflow-hidden"
        >
          <Suspense
            fallback={
              <div className="text-black/30 font-mono text-[8px] uppercase tracking-[0.4em] animate-pulse">
                Booting Neural Sphere...
              </div>
            }
          >
            <ParticleSphere
              className="w-full h-full scale-[0.875] lg:scale-95 opacity-80"
              showCityMarkers
            />
          </Suspense>
        </m.div>
      </div>
    </m.section>
  );
};