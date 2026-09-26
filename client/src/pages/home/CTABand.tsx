import { Accent, PrimaryButton } from "../../components/marketing/kit/Chrome";
import { Reveal } from "../../components/marketing/kit/motion";
import { display } from "../../components/marketing/kit/styles";
import { BOARD, PAPER, hexA } from "../../components/marketing/kit/theme";
import { CONTAINER, SECTION_Y_LG } from "./layout";

export function CTABand({ onDemoClick }: { onDemoClick: () => void }) {
  return (
    <section className={`sched-dark ${SECTION_Y_LG}`} style={{ backgroundColor: BOARD.PAPER, color: PAPER }}>
      <Reveal className={`${CONTAINER} text-center`}>
        <h2 style={{ ...display, fontSize: "clamp(2.75rem, 9vw, 8rem)", lineHeight: 0.95 }}>
          Find your <Accent dark>starting line.</Accent>
        </h2>
        <p className="mx-auto mt-7 max-w-lg text-lg" style={{ color: hexA(PAPER, 0.62), lineHeight: 1.5 }}>
          Tell us where you are. We&rsquo;ll tell you which of the four is the right place to begin.
        </p>
        <div className="mt-10 flex flex-wrap items-center justify-center gap-6">
          <PrimaryButton onClick={onDemoClick} tone="paper">
            Request a demo
          </PrimaryButton>
          <a href="#index" className="sched-link sched-focus rounded text-[15px] font-medium" style={{ color: PAPER }}>
            Browse the four ↑
          </a>
        </div>
      </Reveal>
    </section>
  );
}
