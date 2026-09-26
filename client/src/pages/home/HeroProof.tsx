import { HERO_PROOF, type ProofItem } from "./data";
import { display, mono } from "../../components/marketing/kit/styles";
import { BOARD, PAPER, hexA } from "../../components/marketing/kit/theme";

const LABEL = mono("10.5px", { color: hexA(PAPER, 0.58) });

/**
 * Above-the-fold credibility strip.
 *
 * Renders nothing when HERO_PROOF is empty — a proof strip with no proof is
 * worse than no strip, and this makes "we haven't filled it in yet" a
 * non-shippable state rather than a row of placeholders.
 *
 * See the TODO on HERO_PROOF in data.ts: the current entries are capability
 * claims, not metrics or customers. The three `kind`s exist so swapping in the
 * real assets is a data edit, not a rewrite.
 */
export function HeroProof({
  className = "",
  style,
}: {
  className?: string;
  style?: React.CSSProperties;
}) {
  if (HERO_PROOF.length === 0) return null;

  return (
    <div className={`pt-5 ${className}`} style={style}>
      <ul className="flex flex-wrap items-center gap-x-8 gap-y-3 sm:gap-x-12">
        {HERO_PROOF.map((item, i) => (
          // items-start, not items-center: a claim that wraps to two lines on a
          // narrow viewport would otherwise centre its bullet against both.
          <li key={i} className="flex items-start gap-2.5">
            <ProofEntry item={item} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function ProofEntry({ item }: { item: ProofItem }) {
  if (item.kind === "metric") {
    return (
      <>
        <span
          className="text-[1.6rem] leading-none tabular-nums"
          style={{ ...display, fontWeight: 400, color: PAPER }}
        >
          {item.value}
        </span>
        <span style={LABEL}>
          {item.label}
        </span>
      </>
    );
  }

  if (item.kind === "logo") {
    // Fixed height, never fixed width — logos have wildly different aspect
    // ratios and a shared width makes the wide ones tiny.
    return (
      <img
        src={item.src}
        alt={item.name}
        loading="lazy"
        className="h-6 w-auto opacity-60 grayscale transition-opacity duration-300 hover:opacity-100"
      />
    );
  }

  return (
    <>
      <span
        aria-hidden
        className="w-1 h-1 rounded-full shrink-0 mt-[0.5em]"
        style={{ backgroundColor: BOARD.STAMP }}
      />
      <span style={LABEL}>
        {item.text}
      </span>
    </>
  );
}
