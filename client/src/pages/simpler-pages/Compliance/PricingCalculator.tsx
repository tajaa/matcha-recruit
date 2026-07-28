import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { useMatchaLitePricing, computeLitePriceDollars } from "../../../api/billing/matchaLitePricing";
import { ASH, BONE, LEAF, LINE_D } from "../../home/theme";
import { CONTAINER, EYEBROW, SECTION_Y } from "../../home/layout";
import { Reveal } from "../../home/PageChrome";
import { PRICING_EYEBROW, PRICING_HEADING, PRICING_NOTE } from "./data";

const DEFAULT_HEADCOUNT = 25;

function formatDollars(n: number) {
  return n.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

/**
 * Headcount is the ONLY price input — verified against the backend
 * (`checkout.py` calls `compute_matcha_lite_price_cents(pricing, headcount)`
 * with no jurisdiction term; `jurisdiction_count` reaches Stripe as metadata
 * only). Jurisdiction count stays on the page as a coverage input that
 * prefills signup, never as a price multiplier — presenting it as one would
 * be a real, wrong claim on a live pricing page.
 */
export function PricingCalculator({ onContactClick }: { onContactClick: () => void }) {
  const pricing = useMatchaLitePricing("matcha_compliance");
  const [searchParams] = useSearchParams();
  const [headcount, setHeadcount] = useState(DEFAULT_HEADCOUNT);
  const [jurisdictions, setJurisdictions] = useState(6);

  const minHeadcount = pricing?.min_headcount ?? 1;
  const maxHeadcount = pricing?.max_headcount ?? 300;
  const clampedHeadcount = Math.min(Math.max(headcount, minHeadcount), maxHeadcount);
  const overLimit = headcount > maxHeadcount;
  const underMin = headcount < minHeadcount;
  const price =
    pricing && !overLimit && !underMin ? computeLitePriceDollars(headcount, pricing) : null;

  const signupParams = new URLSearchParams(searchParams);
  signupParams.set("headcount", String(clampedHeadcount));
  signupParams.set("jurisdictions", String(jurisdictions));
  const signupHref = `/compliance/signup?${signupParams.toString()}`;

  return (
    <section className={SECTION_Y}>
      <div className={CONTAINER}>
        <Reveal>
          <div className="max-w-2xl mb-10 sm:mb-12">
            <span className={EYEBROW} style={{ color: ASH }}>
              {PRICING_EYEBROW}
            </span>
            <h2
              className="mt-4 text-[1.7rem] sm:text-[2.1rem] tracking-[-0.015em]"
              style={{ fontFamily: "var(--font-lite)", fontWeight: 300, lineHeight: 1.2, color: BONE }}
            >
              {PRICING_HEADING}
            </h2>
          </div>
        </Reveal>

        <Reveal delayMs={80}>
          <div className="rounded-xl border p-6 sm:p-10 grid grid-cols-1 lg:grid-cols-[1fr_auto] gap-10 items-center" style={{ borderColor: LINE_D }}>
            <div className="flex flex-col gap-7">
              <label className="flex flex-col gap-2.5">
                <span className="flex items-baseline justify-between">
                  <span className="text-[13px] font-mk-mono uppercase tracking-[0.14em]" style={{ color: ASH }}>
                    Employees
                  </span>
                  <span className="tabular-nums" style={{ fontFamily: "var(--font-lite)", color: BONE, fontSize: "1.1rem" }}>
                    {clampedHeadcount}
                  </span>
                </span>
                <input
                  type="range"
                  min={minHeadcount}
                  max={maxHeadcount}
                  value={clampedHeadcount}
                  onChange={(e) => setHeadcount(Number(e.target.value))}
                  className="w-full accent-[#A3C57D]"
                />
              </label>

              <label className="flex flex-col gap-2.5">
                <span className="flex items-baseline justify-between">
                  <span className="text-[13px] font-mk-mono uppercase tracking-[0.14em]" style={{ color: ASH }}>
                    Jurisdictions you operate in
                  </span>
                  <span className="tabular-nums" style={{ fontFamily: "var(--font-lite)", color: BONE, fontSize: "1.1rem" }}>
                    {jurisdictions}
                  </span>
                </span>
                <input
                  type="range"
                  min={1}
                  max={50}
                  value={jurisdictions}
                  onChange={(e) => setJurisdictions(Number(e.target.value))}
                  className="w-full accent-[#A3C57D]"
                />
                <span className="text-[12px]" style={{ color: ASH }}>
                  Coverage, not a price input — every plan tracks every jurisdiction you operate in.
                </span>
              </label>
            </div>

            <div className="flex flex-col items-start lg:items-end gap-4 lg:border-l lg:pl-10" style={{ borderColor: LINE_D }}>
              {overLimit ? (
                <>
                  <div className="text-[15px]" style={{ color: BONE }}>
                    {maxHeadcount}+ employees needs a plan we'll size with you.
                  </div>
                  <button
                    type="button"
                    onClick={onContactClick}
                    className="inline-flex items-center gap-2 px-6 h-12 rounded-full text-[15px] font-medium transition-opacity hover:opacity-90"
                    style={{ backgroundColor: LEAF, color: "#14210B" }}
                  >
                    Talk to us
                  </button>
                </>
              ) : underMin ? (
                <div className="text-[15px]" style={{ color: ASH }}>
                  {minHeadcount}+ employees to price this plan.
                </div>
              ) : (
                <>
                  <div className="flex items-baseline gap-1.5">
                    {price !== null ? (
                      <span
                        className="tabular-nums leading-none"
                        style={{ fontFamily: "var(--font-lite)", fontWeight: 300, fontSize: "3rem", color: BONE }}
                      >
                        ${formatDollars(price)}
                      </span>
                    ) : (
                      <span
                        aria-hidden
                        className="inline-block rounded-md animate-pulse"
                        style={{ width: "6rem", height: "3rem", backgroundColor: "rgba(245,242,237,0.06)" }}
                      />
                    )}
                    <span className="text-[14px]" style={{ color: ASH }}>
                      /month
                    </span>
                  </div>
                  <span className="text-[12px]" style={{ color: ASH }}>
                    {PRICING_NOTE}
                  </span>
                  <Link
                    to={signupHref}
                    className="inline-flex items-center gap-2 px-6 h-12 rounded-full text-[15px] font-medium transition-opacity hover:opacity-90"
                    style={{ backgroundColor: LEAF, color: "#14210B" }}
                  >
                    Start now
                    <ArrowRight className="w-4 h-4" />
                  </Link>
                </>
              )}
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
