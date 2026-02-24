import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
  useLayoutEffect,
} from "react";
import gsap from "gsap";
import ScrollTrigger from "gsap/ScrollTrigger";

import { CinematicNoise } from "./components/CinematicNoise";
import { Navbar } from "./components/Navbar";
import { Hero } from "./sections/Hero";
import { Compliance } from "./sections/Compliance";
import { Interviewer } from "./sections/Interviewer";
import { SystemProtocols } from "./sections/SystemProtocols";
import { Footer } from "./sections/Footer";

gsap.registerPlugin(ScrollTrigger);

export function Landing() {
  const containerRef = useRef<HTMLDivElement>(null);
  const manifestoRef = useRef<HTMLDivElement>(null);
  const systemRef = useRef<HTMLDivElement>(null);

  const [scrolled, setScrolled] = useState(false);
  const [activeSection, setActiveSection] = useState("Core");
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

  useLayoutEffect(() => {
    const ctx = gsap.context(() => {
      // Section Tracking for Telemetry
      const sections = [
        { id: "Hero", trigger: ".hero-trigger" },
        { id: "Compliance", trigger: ".compliance-trigger" },
        { id: "Interviewer", trigger: ".interviewer-trigger" },
        { id: "System", trigger: ".system-trigger" },
      ];

      sections.forEach((section) => {
        ScrollTrigger.create({
          trigger: section.trigger,
          start: "top center",
          onEnter: () => setActiveSection(section.id),
          onEnterBack: () => setActiveSection(section.id),
        });
      });

      // Hero Text Fade Up
      gsap.from(".reveal-text", {
        y: 60,
        opacity: 0,
        stagger: 0.1,
        duration: 1.2,
        ease: "power3.out",
        delay: 0.1,
      });

      // Parallax optimized
      gsap.utils.toArray(".parallax-bg").forEach((bg: any) => {
        gsap.to(bg, {
          yPercent: 15,
          ease: "none",
          scrollTrigger: {
            trigger: bg.parentElement,
            start: "top bottom",
            end: "bottom top",
            scrub: true,
          },
        });
      });

      // Sticky Archive Animation
      const cards = gsap.utils.toArray(".system-card");
      cards.forEach((card: any, i: number) => {
        if (i === cards.length - 1) return;
        gsap.to(card, {
          scale: 0.95,
          opacity: 0.3,
          scrollTrigger: {
            trigger: cards[i + 1] as HTMLElement,
            start: "top bottom",
            end: "top top",
            scrub: true,
          },
        });
      });
    }, containerRef);
    return () => ctx.revert();
  }, []);

  const scrollTo = useCallback((ref: React.RefObject<HTMLDivElement | null>) => {
    ref.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  return (
    <div
      ref={containerRef}
      className="bg-[#0A0E0C] text-[#F0EFEA] selection:bg-[#4ADE80] selection:text-[#0A0E0C] overflow-x-hidden min-h-screen"
    >
      <CinematicNoise />

      <Navbar 
        scrolled={scrolled} 
        activeSection={activeSection}
        scrollTo={scrollTo} 
        manifestoRef={manifestoRef} 
        systemRef={systemRef} 
      />

      <Hero />
      
      <Compliance />

      <Interviewer ref={manifestoRef} />

      <SystemProtocols ref={systemRef} />

      <Footer />
    </div>
  );
}

export default Landing;
