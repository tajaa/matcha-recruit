import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { useMatchaLitePricing, computeLitePriceDollars, type MatchaLiteProductCode } from "../../../api/billing/matchaLitePricing";
import { ASH, BONE, DISPLAY, LEAF, LINE_D } from "../../home/theme";
import { CONTAINER, EYEBROW, SECTION_Y } from "../../home/layout";
import { Reveal } from "../../home/PageChrome";

const DEFAULT_HEADCOUNT = 25;

function formatDollars(n: number) {
  return n.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

/**
 * Two priced product codes, not one variant multiplied off the other —
 * Essentials (`matcha_lite_essentials`) is its own row in `matcha_lite_pricing`
 * (server/app/core/services/matcha_lite_pricing.py), so the toggle re-fetches
 * rather than deriving a discount client-side.
 */
export function PricingCalculator({ onContactClick }: { onContactClick: () => void }) {
  const [essentials, setEssentials] = useState(false);
  const productCode: MatchaLiteProductCode = essentials ? "matcha_lite_essentials" : "matcha_lite";
  const pricing = useMatchaLitePricing(productCode);
  const [searchParams] = useSearchParams();
  const [headcount, setHeadcount] = useState(DEFAULT_HEADCOUNT);

  const minHeadcount = pricing?.min_headcount ?? 1;
  const maxHeadcount = pricing?.max_headcount ?? 300;
  const clampedHeadcount = Math.min(Math.max(headcount, minHeadcount), maxHeadcount);
  const overLimit = headcount > maxHeadcount;
  const underMin = headcount < minHeadcount;
  const price =
    pricing && !overLimit && !underMin ? computeLitePriceDollars(headcount, pricing) : null;

  const signupParams = new URLSearchParams(searchParams);
  signupParams.set("headcount", String(clampedHeadcount));
  signupParams.set("essentials", String(essentials));
  const signupHref = `/lite/signup?${signupParams.toString()}`;

  return (
    <section className={`${SECTION_Y} border-t`} style={{ borderColor: LINE_D }}>
      <div className={CONTAINER}>
        <Reveal>
          <div className="max-w-2xl mb-8 sm:mb-10">
            <span className={EYEBROW} style={{ color: ASH }}>
              Pricing
            </span>
            <h2
              className="mt-4 text-[1.7rem] sm:text-[2.1rem] tracking-[-0.015em]"
              style={{ fontFamily: DISPLAY, fontWeight: 300, lineHeight: 1.2, color: BONE }}
            >
              One price per employee. Billed monthly.
            </h2>
          </div>
        </Reveal>

        <Reveal delayMs={80}>
          <div className="flex gap-2 mb-6">
            {(
              [
                { key: false, label: "Standard" },
                { key: true, label: "Essentials" },
              ] as const
            ).map((opt) => (
              <button
                key={opt.label}
                type="button"
                onClick={() => setEssentials(opt.key)}
                className="px-4 h-9 rounded-full text-[13px] font-medium transition-colors"
                style={{
                  backgroundColor: essentials === opt.key ? LEAF : "transparent",
                  color: essentials === opt.key ? "#14210B" : ASH,
                  border: `1px solid ${essentials === opt.key ? LEAF : LINE_D}`,
                }}
              >
                {opt.label}
              </button>
            ))}
          </div>

          <div
            className="rounded-xl border p-6 sm:p-10 grid grid-cols-1 lg:grid-cols-[1fr_auto] gap-10 items-center"
            style={{ borderColor: LINE_D }}
          >
            <div className="flex flex-col gap-3">
              <label className="flex flex-col gap-2.5">
                <span className="flex items-baseline justify-between">
                  <span className="text-[13px] font-mk-mono uppercase tracking-[0.14em]" style={{ color: ASH }}>
                    Employees
                  </span>
                  <span className="tabular-nums" style={{ fontFamily: DISPLAY, color: BONE, fontSize: "1.1rem" }}>
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
              <span className="text-[12px]" style={{ color: ASH }}>
                {essentials
                  ? "Incident reporting only — no employee roster, no CSV/HRIS import, no OSHA logs."
                  : "Incident reporting, roster import, IR analysis, and OSHA logs."}
              </span>
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
                        style={{ fontFamily: DISPLAY, fontWeight: 300, fontSize: "3rem", color: BONE }}
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
                    Billed monthly · exact price confirmed at signup
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
