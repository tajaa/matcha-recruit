import { lazy, Suspense, useEffect, useState } from "react";
import MarketingFooter from "../landing/MarketingFooter";
import { useSEO } from "../../hooks/useSEO";
import { HOME_V2_JSON_LD } from "./data";
import { CREAM } from "./theme";
import HomeV2Nav from "./Nav";
import { Hero } from "./Hero";
import { paperSurface } from "./PaperGrain";

// Same latched-lazy pattern as pages/home/index.tsx:16-20,59-78 — mount on
// first open so a visitor who never clicks a demo CTA never pulls the chunk,
// then leave it mounted so the modal's own exit animation can play on close.
const PricingContactModal = lazy(() =>
  import("../../components/marketing/PricingContactModal").then((m) => ({
    default: m.PricingContactModal,
  })),
);

// Mirrors pages/home/PageChrome.tsx's useMarketingNoir — sets the cream twin
// of data-marketing-noir (index.css) while this page is mounted, so overscroll
// bounce and anchor-jump scrolling match the page instead of defaulting dark.
function useMarketingCream() {
  useEffect(() => {
    document.documentElement.setAttribute("data-marketing-cream", "");
    return () => document.documentElement.removeAttribute("data-marketing-cream");
  }, []);
}

export default function HomeV2() {
  const [isPricingOpen, setIsPricingOpen] = useState(false);
  const [hasOpenedPricing, setHasOpenedPricing] = useState(false);
  const openPricing = () => {
    setHasOpenedPricing(true);
    setIsPricingOpen(true);
  };

  useMarketingCream();

  useSEO({
    title: "Matcha — Managing Your Risk, Before Your Risk Manages You",
    description:
      "Incident reporting, employee relations, and compliance in one system — for companies who'd rather get ahead of risk than clean up after it.",
    canonical: "https://hey-matcha.com/home-v2",
    jsonLd: HOME_V2_JSON_LD,
    noindex: true,
  });

  return (
    <div style={paperSurface(CREAM)} className="min-h-screen">
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
          <PricingContactModal isOpen={isPricingOpen} onClose={() => setIsPricingOpen(false)} />
        </Suspense>
      )}

      <HomeV2Nav onDemoClick={openPricing} />
      <Hero onDemoClick={openPricing} />

      <MarketingFooter newsletterVariant="matcha" />
    </div>
  );
}
