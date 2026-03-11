import { lazy, Suspense, useState, useEffect, useRef } from "react";
import { m, type Variants } from "framer-motion";
import { TelemetryBadge } from "../components/TelemetryBadge";
import { TechnicalSpecs } from "../components/TechnicalSpecs";
import { AsciiHalftone } from "../components/AsciiHalftone";
import { useInViewport } from "../hooks/useInViewport";
import { fonts } from "../constants";

const ParticleSphere = lazy(() => import("../../../components/ParticleSphere"));

const MATRIX_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZｦｧｨｩｪｫｬｭｮｯｰｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ0123456789!@#$%&';

function GlitchText({ text, cycleWords, className, style }: { text: string; cycleWords?: string[]; className?: string; style?: React.CSSProperties }) {
  const [chars, setChars] = useState<string[]>(() =>
    text.split('').map(c => (c === ' ' || c === '.') ? c : MATRIX_CHARS[Math.floor(Math.random() * MATRIX_CHARS.length)])
  );
  const [isGlitching, setIsGlitching] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const currentDisplayRef = useRef(text);

  const decodeInto = (target: string, onDone: () => void) => {
    const targetArr = target.split('');
    let progress = 0;
    const decode = setInterval(() => {
      setChars(prev =>
        prev.map((_, i) => {
          const t = targetArr[i] ?? ' ';
          if (t === ' ' || t === '.') return t;
          if (i < progress) return t;
          return MATRIX_CHARS[Math.floor(Math.random() * MATRIX_CHARS.length)];
        })
      );
      progress += 0.5;
      if (progress >= targetArr.length) {
        clearInterval(decode);
        setChars(targetArr);
        currentDisplayRef.current = target;
        onDone();
      }
    }, 45);
  };

  // Decode left-to-right on mount
  useEffect(() => {
    decodeInto(text, () => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Periodic glitch — paused when off-screen
  const { ref: glitchRef, isVisible: glitchVisible } = useInViewport();
  const glitchVisibleRef = useRef(glitchVisible);
  glitchVisibleRef.current = glitchVisible;

  useEffect(() => {
    const allPhrases = cycleWords ? [...cycleWords, text] : [text];
    let phraseIndex = 0;

    const runGlitchThenDecode = (target: string, onDone: () => void) => {
      setIsGlitching(true);
      let ticks = 0;
      const maxTicks = 5 + Math.floor(Math.random() * 5);
      intervalRef.current = setInterval(() => {
        const src = currentDisplayRef.current;
        setChars(
          Array.from({ length: Math.max(src.length, target.length) }, (_, i) => {
            const c = src[i] ?? ' ';
            if (c === ' ' || c === '.') return c;
            return Math.random() > 0.35 ? c : MATRIX_CHARS[Math.floor(Math.random() * MATRIX_CHARS.length)];
          })
        );
        ticks++;
        if (ticks >= maxTicks) {
          clearInterval(intervalRef.current!);
          setIsGlitching(false);
          decodeInto(target, onDone);
        }
      }, 55);
    };

    const scheduleNext = () => {
      const delay = phraseIndex === 0 ? 2800 + Math.random() * 4000 : 900 + Math.random() * 600;
      timeoutRef.current = setTimeout(() => {
        if (!glitchVisibleRef.current) { scheduleNext(); return; }
        const target = allPhrases[phraseIndex % allPhrases.length];
        phraseIndex++;
        runGlitchThenDecode(target, () => {
          if (phraseIndex < allPhrases.length) {
            scheduleNext();
          } else {
            phraseIndex = 0;
            scheduleNext();
          }
        });
      }, delay);
    };

    scheduleNext();
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, cycleWords]);

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
        <div className="absolute inset-0 bg-zinc-600" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[1200px] h-[800px] rounded-full mix-blend-multiply" style={{ background: "radial-gradient(circle, rgba(0,0,0,0.03) 0%, transparent 70%)" }} />
        <div className="absolute top-0 left-0 w-full h-full opacity-[0.06] pointer-events-none bg-[url('/textures/asfalt-light.png')]" />
      </div>

      <AsciiHalftone />

      <div className="relative z-10 w-full max-w-[1600px] mx-auto grid lg:grid-cols-[1fr_0.8fr] gap-12 items-center">
        <div className="flex flex-col items-center lg:items-start relative z-10 py-20 text-center lg:text-left">
          <m.div variants={itemVariants} className="flex items-center gap-4 justify-center lg:justify-start">
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
          
          <div className="mt-10 relative z-10 px-20 py-16 -mx-20 w-fit">
            <m.h1 variants={itemVariants} className="leading-[0.9] tracking-[-0.04em] max-w-2xl">
              <span
                className="block mb-2 text-[1.875rem] md:text-[3rem] lg:text-[3.75rem] font-bold uppercase text-white"
                style={{ fontFamily: fonts.display, letterSpacing: '0.05em' }}
              >
                Workforce
              </span>
              <GlitchText
                text="Intelligence."
                cycleWords={["Compliance.", "Risk Assessment.", "Risk Management."]}
                className="block text-[2.25rem] md:text-[3.75rem] lg:text-[4.5rem] italic font-light text-white/90"
                style={{
                  fontFamily: fonts.serif,
                }}
              />
            </m.h1>

            <m.div variants={itemVariants} className="space-y-10 mt-10">
              <p
                className="text-white/80 text-lg md:text-xl lg:text-2xl font-semibold leading-relaxed w-fit whitespace-nowrap"
                style={{ fontFamily: fonts.sans }}
              >
                Increase your <span className="text-amber-400">signal to noise ratio</span>.
              </p>
            
            <div className="flex flex-wrap gap-6 pt-2 justify-center lg:justify-start">
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
          className="hidden lg:flex relative h-[66vh] w-full items-center justify-center z-0 group overflow-hidden"
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