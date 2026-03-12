import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { LazyMotion, domAnimation } from "framer-motion";

import { CinematicNoise } from "./components/CinematicNoise";
import { Navbar } from "./components/Navbar";
import { PricingContactModal } from "./components/PricingContactModal";
import { Hero } from "./sections/Hero";
import { Compliance } from "./sections/Compliance";
import { ERCopilot } from "./sections/ERCopilot";
import { RiskSnapshot } from "./sections/RiskSnapshot";
import { DynamicHandbooks } from "./sections/DynamicHandbooks";
import { Footer } from "./sections/Footer";

export function Landing() {
  const manifestoRef = useRef<HTMLDivElement>(null);

  const [scrolled, setScrolled] = useState(false);
  const [activeSection, setActiveSection] = useState("Core");
  const [isPricingModalOpen, setIsPricingModalOpen] = useState(false);
  const scrolledRef = useRef(false);

  useEffect(() => {
    let ticking = false;
    let frameId = 0;
    const updateScrolled = () => {
      const nextScrolled = window.scrollY > 50;
      if (nextScrolled !== scrolledRef.current) {
        scrolledRef.current = nextScrolled;
        setScrolled(nextScrolled);
      }
      ticking = false;
    };

    const handleScroll = () => {
      if (!ticking) {
        frameId = window.requestAnimationFrame(updateScrolled);
        ticking = true;
      }
    };

    updateScrolled();
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      if (frameId) {
        window.cancelAnimationFrame(frameId);
      }
      window.removeEventListener("scroll", handleScroll);
    };
  }, []);

  useEffect(() => {
    const sectionMap = [
      { id: "Hero", selector: ".hero-trigger" },
      { id: "Compliance", selector: ".compliance-trigger" },
    ];
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const s = sectionMap.find(s => entry.target.matches(s.selector));
            if (s) setActiveSection(s.id);
          }
        });
      },
      { rootMargin: "-50% 0px" }
    );
    sectionMap.forEach(s => {
      const el = document.querySelector(s.selector);
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, []);

  const scrollTo = useCallback((ref: React.RefObject<HTMLDivElement | null>) => {
    ref.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  return (
    <div
      className="bg-[#0A0E0C] text-[#F0EFEA] selection:bg-[#4ADE80] selection:text-[#0A0E0C] overflow-x-hidden min-h-screen"
    >
      <LazyMotion features={domAnimation}>
        <CinematicNoise />

        <Navbar
          scrolled={scrolled}
          activeSection={activeSection}
          scrollTo={scrollTo}
          manifestoRef={manifestoRef}
          onPricingClick={() => setIsPricingModalOpen(true)}
        />

        <PricingContactModal
          isOpen={isPricingModalOpen}
          onClose={() => setIsPricingModalOpen(false)}
        />

        <Hero onContactClick={() => setIsPricingModalOpen(true)} />

        <Footer />
      </LazyMotion>
    </div>
  );
}

export default Landing;
