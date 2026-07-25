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
 * The product showcase — its own section rather than a block inside the hero
 * (2026-07-25), but deliberately NOT below the fold.
 *
 * Two forces: the carousel competed with the email capture when both sat in one
 * hero block, and it is also the single most persuasive thing on the page — a
 * visitor who never sees a product surface has been sold nothing. The
 * resolution is sequence, not exile: the hero is content-height (no svh floor,
 * no chevron), and this section's top padding is small enough that the eyebrow
 * plus the top ~300px of the instrument sit inside a 800px fold. The capture
 * gets the visitor's first, undivided beat; the product is visible in the same
 * glance and finishes on one scroll gesture.
 *
 * So the padding here is load-bearing, not rhythm: the shared SECTION_Y scale
 * (py-20 sm:py-28 md:py-32) would push the carousel back off the fold.
 */
export function ShowcaseSection() {
  return (
    <section id="showcase" className="scroll-mt-16 pt-9 sm:pt-11 md:pt-12">
      <div className={CONTAINER}>
        <Reveal>
          <div className="flex items-baseline justify-between mb-6">
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
