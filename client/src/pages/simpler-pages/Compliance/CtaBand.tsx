import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { ASH, BONE, LEAF, NOIR } from "../../home/theme";
import { CONTAINER, SECTION_Y_LG } from "../../home/layout";
import { Reveal } from "../../home/PageChrome";
import { CLOSING_HEADING, CLOSING_SUB } from "./data";

// Primary flips to self-serve here too — the old page's only CTA was "Contact
// us", which contradicted a product visitors can start without a sales call.
export function CtaBand({ onContactClick }: { onContactClick: () => void }) {
  return (
    <section className={SECTION_Y_LG}>
      <Reveal className={`${CONTAINER} text-center`}>
        <h2
          className="tracking-[-0.02em]"
          style={{
            fontFamily: "var(--font-lite)",
            fontWeight: 300,
            lineHeight: 1,
            color: BONE,
            fontSize: "clamp(2.5rem, 7vw, 5.5rem)",
          }}
        >
          {CLOSING_HEADING}
        </h2>
        <p className="mt-6 mx-auto max-w-lg text-lg" style={{ color: ASH, lineHeight: 1.5 }}>
          {CLOSING_SUB}
        </p>
        <div className="mt-10 flex flex-wrap items-center justify-center gap-5">
          <Link
            to="/compliance/signup"
            className="inline-flex items-center gap-2 px-8 rounded-full text-base font-medium transition-all duration-300 hover:-translate-y-0.5 hover:shadow-[0_18px_44px_-16px_rgba(163,197,125,0.45)] active:translate-y-0 active:shadow-none"
            style={{ backgroundColor: LEAF, color: NOIR, height: 56 }}
          >
            Start now
            <ArrowRight className="w-4 h-4" />
          </Link>
          <button
            type="button"
            onClick={onContactClick}
            className="inline-flex items-center text-base transition-opacity hover:opacity-60 cursor-pointer"
            style={{ color: BONE }}
          >
            Talk to sales
          </button>
        </div>
      </Reveal>
    </section>
  );
}
