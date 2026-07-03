import { useState } from "react";
import MarketingNav from "../landing/MarketingNav";
import MarketingFooter from "../landing/MarketingFooter";
import { PricingContactModal } from "../../components/PricingContactModal";
import { useSEO } from "../../hooks/useSEO";
import { HOME_JSON_LD } from "./data";
import { BONE, NOIR } from "./theme";
import { GrainOverlay, PageStyle } from "./PageChrome";
import { Hero } from "./Hero";
import { ProductIndex } from "./ProductIndex";
import { Manifesto } from "./Manifesto";
import { CTABand } from "./CTABand";

export default function Home() {
  const [isPricingOpen, setIsPricingOpen] = useState(false);

  useSEO({
    title: "Matcha — Full-Service HR: Platform, Lite, Compliance & Consulting",
    description:
      "Full-service HR for modern companies — an agentic risk & compliance platform, Matcha Lite for small teams, multi-state compliance tracking, and senior advisory. One standard of rigor across software and people.",
    canonical: "https://hey-matcha.com/",
    jsonLd: HOME_JSON_LD,
  });

  return (
    <div
      style={{ backgroundColor: NOIR, color: BONE }}
      className="min-h-screen overflow-x-hidden"
    >
      <PageStyle />
      <GrainOverlay />

      <PricingContactModal
        isOpen={isPricingOpen}
        onClose={() => setIsPricingOpen(false)}
      />
      <MarketingNav onDemoClick={() => setIsPricingOpen(true)} />

      <Hero />
      <ProductIndex />
      <Manifesto />
      <CTABand onDemoClick={() => setIsPricingOpen(true)} />

      <div style={{ backgroundColor: BONE, color: "var(--color-ivory-ink)" }}>
        <MarketingFooter newsletterVariant="matcha" />
      </div>
    </div>
  );
}
