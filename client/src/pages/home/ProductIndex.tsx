import { useState } from "react";
import { Link } from "react-router-dom";
import { PRODUCTS } from "./data";
import { CellLabel } from "../../components/marketing/kit/Chrome";
import { Reveal } from "../../components/marketing/kit/motion";
import { display, mono } from "../../components/marketing/kit/styles";
import { BOARD, INK, INK_SOFT, PAPER, STAMP, hexA } from "../../components/marketing/kit/theme";
import { CONTAINER, SECTION_Y } from "./layout";

const LINE = hexA(INK, 0.1);

export function ProductIndex() {
  const [hovered, setHovered] = useState<number | null>(null);

  return (
    <section id="index" className={`scroll-mt-16 ${SECTION_Y}`}>
      <div className={CONTAINER}>
        <Reveal>
          <div className="flex items-baseline justify-between mb-2">
            <h2>
              <CellLabel n="02">Four ways in</CellLabel>
            </h2>
            <span style={mono("10px", { color: INK_SOFT })}>Index</span>
          </div>
        </Reveal>

        <div className="border-t" style={{ borderColor: LINE }}>
          {PRODUCTS.map((p, i) => {
            const active = hovered === i;
            return (
              <Reveal key={p.name} delay={Math.min(i * 70, 210)}>
              <Link
                to={p.to}
                onMouseEnter={() => setHovered(i)}
                onMouseLeave={() => setHovered(null)}
                className="group relative grid grid-cols-[auto_1fr] sm:grid-cols-[auto_1fr_auto] items-center gap-x-5 sm:gap-x-10 border-b px-2 sm:px-6 py-7 sm:py-10 transition-colors duration-300"
                style={{
                  borderColor: LINE,
                  backgroundColor: active ? INK : "transparent",
                  color: active ? PAPER : INK,
                }}
              >
                <span
                  className="self-start pt-2 sm:pt-4 transition-colors duration-300"
                  style={mono("12px", { letterSpacing: "0.04em", color: active ? BOARD.STAMP : STAMP })}
                >
                  {p.n}
                </span>

                <div className="min-w-0">
                  <h3
                    className="transition-transform duration-300 group-hover:translate-x-2"
                    style={{ ...display, lineHeight: 0.95, fontSize: "clamp(2.25rem, 7vw, 5.5rem)" }}
                  >
                    {p.name}
                  </h3>
                  <p
                    className="mt-3 max-w-2xl text-[15px] sm:text-lg transition-colors duration-300"
                    style={{
                      color: active ? hexA(PAPER, 0.72) : INK_SOFT,
                      lineHeight: 1.5,
                    }}
                  >
                    {p.blurb}
                  </p>
                </div>

                <span
                  className="hidden sm:inline-flex items-center gap-2 justify-self-end transition-all duration-300"
                  style={mono("10.5px", { color: "inherit", opacity: active ? 1 : 0.55 })}
                >
                  Enter
                  <span
                    className="transition-transform duration-300 group-hover:translate-x-1.5"
                    aria-hidden
                  >
                    →
                  </span>
                </span>
              </Link>
              </Reveal>
            );
          })}
        </div>
      </div>
    </section>
  );
}
