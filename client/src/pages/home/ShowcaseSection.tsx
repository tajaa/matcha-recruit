import { lazy, Suspense } from "react";
import { ASH } from "./theme";
import { CONTAINER, EYEBROW, EYEBROW_END } from "./layout";
import { Reveal } from "./PageChrome";

// The carousel and its four instruments are the ONLY framer-motion importers on
// the apex route (~60-110 KB gz). Lazy-loading keeps framer out of the eager `/`
// chunk — and now that the carousel lives below the fold rather than inside the
// hero, the boundary is honest: it genuinely isn't needed for first paint.
const ProductCarousel = lazy(() =>
  import("./ProductCarousel").then((m) => ({ default: m.ProductCarousel })),
);

/**
 * The product showcase, moved out of the hero (2026-07-25).
 *
 * It is the strongest asset on the page, and burying it one scroll gesture down
 * is a real cost — but keeping it above the fold cost more. The hero is now
 * headline + subhead + capture + proof, which is already a full fold at 800px
 * viewport height; with the carousel in there too, `min-h-[100svh]` was a
 * broken promise and the conversion element drifted toward the fold edge on
 * 13" laptops. The carousel also competed with the capture at the exact moment
 * of decision.
 *
 * Reversible: drop <ProductCarousel /> back into Hero's container if it tests
 * worse.
 */
export function ShowcaseSection() {
  return (
    <section id="showcase" className="scroll-mt-16 pt-16 sm:pt-20 md:pt-24">
      <div className={CONTAINER}>
        <Reveal>
          <div className="flex items-baseline justify-between mb-8">
            <h2 className={EYEBROW} style={{ color: ASH }}>
              What it looks like
            </h2>
            <span className={EYEBROW_END} style={{ color: ASH }}>
              Showcase
            </span>
          </div>
          {/* No spinner: the slot is blank during the reveal transition anyway,
              and a fallback would flash where nothing was shown. */}
          <Suspense fallback={null}>
            <ProductCarousel />
          </Suspense>
        </Reveal>
      </div>
    </section>
  );
}
