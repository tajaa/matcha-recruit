import { lazy, Suspense, useState } from "react";
import MarketingNav from "../landing/MarketingNav";
import MarketingFooter from "../landing/MarketingFooter";
import { useSEO } from "../../hooks/useSEO";
import { HOME_JSON_LD } from "./data";
import { Grain, KitStyles } from "../../components/marketing/kit/Chrome";
import { useMarketingBoard } from "../../components/marketing/kit/hooks";
import { BODY, INK, PAPER } from "../../components/marketing/kit/theme";
// PageStyle still carries the instruments' keyframes and the hero's
// landscape rules.
import { PageStyle } from "./PageChrome";
import { Hero } from "./Hero";
import { ShowcaseSection } from "./ShowcaseSection";
import { ProductIndex } from "./ProductIndex";
import { Manifesto } from "./Manifesto";
import { CTABand } from "./CTABand";

// Second framer-motion importer on the apex route, and it renders nothing until
// the visitor clicks a demo CTA — so it has no business in the eager chunk.
const PricingContactModal = lazy(() =>
  import("../../components/marketing/PricingContactModal").then((m) => ({
    default: m?.PricingContactModal ?? (() => null),
  })),
);

export default function Home() {
  const [isPricingOpen, setIsPricingOpen] = useState(false);
  // One-way latch: true from the first open onward. See the mount note below.
  const [hasOpenedPricing, setHasOpenedPricing] = useState(false);
  const openPricing = () => {
    setHasOpenedPricing(true);
    setIsPricingOpen(true);
  };

  useMarketingBoard();

  useSEO({
    title: "Matcha — Full-Service HR: Platform, Lite, Compliance & Consulting",
    description:
      "Full-service HR for modern companies — an agentic risk & compliance platform, Matcha Lite for small teams, multi-state compliance tracking, and senior advisory. One standard of rigor across software and people.",
    canonical: "https://hey-matcha.com/",
    jsonLd: HOME_JSON_LD,
  });

  return (
    <div
      style={{ backgroundColor: PAPER, color: INK, fontFamily: BODY }}
      className="home-root sched-root min-h-screen overflow-x-clip"
    >
      <KitStyles />
      <PageStyle />
      <Grain />

      {/* Latched, not `isPricingOpen &&`: the modal owns an <AnimatePresence>
          keyed on isOpen, so unmounting the moment it closes would cut its exit
          animation. Mount on first open, then leave it mounted and let isOpen
          drive it — the lazy chunk still never loads for a visitor who never
          clicks a demo CTA, which is the whole point.

          The Suspense fallback is not null: this is the apex conversion path,
          and on a slow connection a null fallback means the demo CTA visibly
          does nothing until the chunk lands. A backdrop + spinner shows the
          click registered. */}
      {hasOpenedPricing && (
        <Suspense
          fallback={
            isPricingOpen ? (
              <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60">
                <div
                  className="h-8 w-8 animate-spin rounded-full border-2 border-white/25 border-t-white/90"
                  role="status"
                  aria-label="Loading"
                />
              </div>
            ) : null
          }
        >
          <PricingContactModal
            isOpen={isPricingOpen}
            onClose={() => setIsPricingOpen(false)}
          />
        </Suspense>
      )}
      <MarketingNav
        onDemoClick={openPricing}
        transparentAtTop
      />

      <Hero />
      <ShowcaseSection />
      <ProductIndex />
      <Manifesto />
      <CTABand onDemoClick={openPricing} />

      <MarketingFooter />
    </div>
  );
}
