import { lazy, Suspense } from "react";
import { TelemetryBadge } from "../components/TelemetryBadge";
import { TechnicalSpecs } from "../components/TechnicalSpecs";
import { fonts } from "../constants";

const ParticleSphere = lazy(() => import("../../../components/ParticleSphere"));

export const Hero = () => {
  return (
    <section className="hero-trigger relative min-h-screen flex flex-col justify-center px-6 md:px-16 overflow-hidden">
      <div className="absolute inset-0 z-0 overflow-hidden pointer-events-none">
        <div
          className="parallax-bg absolute -inset-[10%] bg-cover bg-center opacity-[0.18]"
          style={{
            backgroundImage: `url('https://images.unsplash.com/photo-1419242902214-272b3f66ee7a?q=80&w=3500&auto=format&fit=crop')`,
          }}
        />
        <div className="absolute inset-0 bg-gradient-to-t from-[#0A0E0C] via-[#0A0E0C]/80 to-transparent" />
        <div className="absolute inset-0 bg-gradient-to-r from-[#0A0E0C] via-transparent to-transparent" />
      </div>

      <div className="relative z-20 w-full max-w-[1600px] mx-auto grid lg:grid-cols-2 gap-12 items-center">
        <div className="flex flex-col items-start relative z-10 pt-20">
          <div className="flex items-center">
            <TelemetryBadge text="Core System v2.4 Online" active />
            <TechnicalSpecs 
              title="Workforce Intelligence"
              specs={[
                "Real-time neural rendering",
                "Latent data processing",
                "Asynchronous state sync",
                "GPU-accelerated cinematography"
              ]}
            />
          </div>
          <h1 className="mt-8 leading-[0.85] tracking-tighter mix-blend-lighten">
            <span
              className="reveal-text block text-[4rem] md:text-[6.5rem] font-bold uppercase"
              style={{
                fontFamily: fonts.sans,
                willChange: "transform, opacity",
              }}
            >
              Workforce
            </span>
            <span
              className="reveal-text block text-[5rem] md:text-[7.5rem] italic font-light text-[#D95A38]"
              style={{
                fontFamily: fonts.serif,
                willChange: "transform, opacity",
              }}
            >
              Intelligence.
            </span>
          </h1>
          <p
            className="reveal-text mt-8 text-[#F0EFEA]/60 text-lg md:text-xl font-light leading-relaxed max-w-xl"
            style={{ fontFamily: fonts.sans }}
          >
            The operating system for modern workforce management. <br />
            Stripped of administrative noise. Engineered for biological
            clarity.
          </p>
        </div>

        <div
          className="relative h-[50vh] lg:h-[80vh] w-full flex items-center justify-center z-0 mt-12 lg:mt-0"
          style={{ transform: "translateZ(0)" }}
        >
          <Suspense
            fallback={
              <div className="text-[#4ADE80] font-mono text-[10px] uppercase tracking-widest animate-pulse flex flex-col items-center gap-4">
                <div className="w-8 h-8 border border-[#4ADE80] rounded-full border-t-transparent animate-spin" />
                Initializing Neural Sphere...
              </div>
            }
          >
            <div className="absolute inset-0 bg-[#4ADE80]/5 blur-[100px] rounded-full mix-blend-screen pointer-events-none" />
            <ParticleSphere
              className="w-full h-full scale-110 lg:scale-125"
              showCityMarkers
            />
          </Suspense>
        </div>
      </div>
    </section>
  );
};
