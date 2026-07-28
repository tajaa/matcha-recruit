import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { ChevronDown, Menu, X } from "lucide-react";
import { CREAM, CREAM_HI, INK, INK_SOFT, LINE, MATCHA, MATCHA_MID, MATCHA_WASH, SANS } from "./theme";
import { paperSurface } from "./PaperGrain";
import { NAV_LINKS, PLATFORM_MENU, PLATFORM_MENU_FOOTER } from "./data";

interface Props {
  onDemoClick?: () => void;
}

// Cream twin of the leaf mark in landing/MarketingNav.tsx:91-98 — same
// geometry (one squared corner turns the circle into a leaf), MATCHA gradient
// instead of the light-on-dark pair. This shape is the page's motif; the
// mega-menu panel and the CTA button echo the same squared corner below.
function LeafMark() {
  return (
    <span
      aria-hidden
      className="block w-[15px] h-[15px] shrink-0 transition-transform duration-500 ease-out group-hover:rotate-[135deg]"
      style={{
        background: `linear-gradient(135deg, ${MATCHA_MID} 0%, ${MATCHA} 100%)`,
        borderRadius: "50% 2px 50% 50%",
      }}
    />
  );
}

export default function HomeV2Nav({ onDemoClick }: Props) {
  const [platformOpen, setPlatformOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const { pathname } = useLocation();
  const triggerRef = useRef<HTMLButtonElement>(null);

  const closeAll = () => {
    setPlatformOpen(false);
    setMobileOpen(false);
  };

  useEffect(() => {
    if (!platformOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setPlatformOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [platformOpen]);

  return (
    <>
      <nav
        className="sticky left-0 right-0 top-0 z-50"
        style={{
          ...paperSurface(CREAM),
          borderBottom: `1px solid ${LINE}`,
        }}
      >
        <div className="relative max-w-[1440px] mx-auto flex items-center justify-between px-6 sm:px-10 h-[72px]">
          <Link to="/home-v2" onClick={closeAll} className="group flex items-center gap-2.5">
            <LeafMark />
            <span
              className="text-[18px] leading-none tracking-[0.18em]"
              style={{ fontFamily: "var(--font-display)", fontWeight: 500, color: INK }}
            >
              MATCHA
            </span>
          </Link>

          <div className="hidden md:flex items-center gap-8">
            <div
              className="relative"
              onMouseEnter={() => setPlatformOpen(true)}
              onMouseLeave={() => setPlatformOpen(false)}
            >
              <button
                ref={triggerRef}
                type="button"
                onClick={() => setPlatformOpen((v) => !v)}
                className="inline-flex items-center gap-1 text-[13.5px] transition-colors duration-200 cursor-pointer"
                style={{ color: platformOpen ? INK : INK_SOFT, fontFamily: SANS }}
                aria-expanded={platformOpen}
                aria-haspopup="true"
              >
                Platform
                <ChevronDown
                  className="w-3.5 h-3.5 transition-transform duration-200"
                  style={{ transform: platformOpen ? "rotate(180deg)" : "none" }}
                />
              </button>

              {platformOpen && (
                <div className="absolute left-1/2 -translate-x-1/2 top-full pt-3">
                  <div
                    className="w-[520px] p-6 grid grid-cols-2 gap-x-0 gap-y-6"
                    style={{
                      backgroundColor: CREAM_HI,
                      border: `1px solid ${LINE}`,
                      borderRadius: "4px",
                      boxShadow: "0 16px 32px -20px rgba(20,21,15,0.14)",
                    }}
                  >
                    {PLATFORM_MENU.map((group, gi) => (
                      <div
                        key={group.heading}
                        className={gi === 0 ? "pr-8" : "pl-8"}
                        style={gi === 1 ? { borderLeft: `1px solid ${LINE}` } : undefined}
                      >
                        <div
                          className="text-[10.5px] font-mk-mono uppercase tracking-[0.18em] mb-3"
                          style={{ color: INK_SOFT }}
                        >
                          {group.heading}
                        </div>
                        <div className="flex flex-col gap-1 -mx-2.5">
                          {group.rows.map((row) => (
                            <Link
                              key={row.label}
                              to={row.to}
                              onClick={closeAll}
                              className="block rounded-[4px] px-2.5 py-2 transition-colors duration-150 hover:[background-color:var(--hv2-row-hover)]"
                              style={{ ["--hv2-row-hover" as string]: MATCHA_WASH }}
                            >
                              <div
                                className="text-[15px]"
                                style={{ fontFamily: "var(--font-display)", color: INK }}
                              >
                                {row.label}
                              </div>
                              <div className="mt-0.5 text-[12.5px] leading-snug" style={{ color: INK_SOFT, fontFamily: SANS }}>
                                {row.caption}
                              </div>
                            </Link>
                          ))}
                        </div>
                      </div>
                    ))}

                    <div
                      className="col-span-2 pt-4 flex items-center justify-between"
                      style={{ borderTop: `1px solid ${LINE}` }}
                    >
                      <span className="text-[12.5px]" style={{ color: INK_SOFT }}>
                        Not sure where to start?
                      </span>
                      <Link
                        to={PLATFORM_MENU_FOOTER.to}
                        onClick={closeAll}
                        className="text-[13px] font-medium transition-opacity hover:opacity-70"
                        style={{ color: MATCHA }}
                      >
                        {PLATFORM_MENU_FOOTER.label} →
                      </Link>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {NAV_LINKS.map((link) => {
              const active = pathname === link.to;
              return (
                <Link
                  key={link.to}
                  to={link.to}
                  className="text-[13.5px] transition-colors duration-200"
                  style={{ color: active ? INK : INK_SOFT, fontFamily: SANS }}
                >
                  {link.label}
                </Link>
              );
            })}
          </div>

          <div className="flex items-center gap-4">
            <Link
              to="/login"
              className="hidden md:inline text-[13.5px] transition-colors duration-200"
              style={{ color: INK_SOFT }}
            >
              Login
            </Link>
            <button
              onClick={onDemoClick}
              className="hidden sm:inline-flex items-center h-9 px-5 text-[13px] font-medium cursor-pointer transition-opacity hover:opacity-90"
              style={{
                backgroundColor: MATCHA,
                color: INK,
                borderRadius: "6px",
              }}
            >
              Get a demo
            </button>
            <button
              onClick={() => setMobileOpen(!mobileOpen)}
              className="md:hidden inline-flex items-center justify-center w-10 h-10 -mr-2"
              style={{ color: INK }}
              aria-label={mobileOpen ? "Close menu" : "Open menu"}
            >
              {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
        </div>
      </nav>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 md:hidden overflow-y-auto" style={paperSurface(CREAM)}>
          <div className="pt-24 px-6 pb-12 flex flex-col gap-1">
            <div
              className="mb-1 text-[11px] uppercase tracking-[0.18em] font-mk-mono"
              style={{ color: INK_SOFT }}
            >
              Platform
            </div>
            {PLATFORM_MENU.flatMap((g) => g.rows).map((row) => (
              <Link
                key={row.label}
                to={row.to}
                onClick={closeAll}
                className="py-3.5 text-xl border-b"
                style={{ fontFamily: "var(--font-display)", color: INK, borderColor: LINE }}
              >
                {row.label}
              </Link>
            ))}

            <div
              className="mt-6 mb-1 text-[11px] uppercase tracking-[0.18em] font-mk-mono"
              style={{ color: INK_SOFT }}
            >
              Explore
            </div>
            {NAV_LINKS.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                onClick={closeAll}
                className="py-3 text-lg border-b"
                style={{ color: INK, borderColor: LINE }}
              >
                {link.label}
              </Link>
            ))}

            <Link to="/login" onClick={closeAll} className="mt-6 py-3 text-lg" style={{ color: INK }}>
              Login
            </Link>
            <button
              onClick={() => {
                closeAll();
                onDemoClick?.();
              }}
              className="mt-4 inline-flex items-center justify-center px-6 h-12 text-base font-medium cursor-pointer"
              style={{ backgroundColor: MATCHA, color: INK, borderRadius: "6px" }}
            >
              Get a demo
            </button>
          </div>
        </div>
      )}
    </>
  );
}
