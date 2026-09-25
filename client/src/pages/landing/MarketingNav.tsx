import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Menu, X, ChevronDown } from "lucide-react";
import { BOARD, BODY, INK, PAPER, STAMP, hexA } from "../../components/marketing/kit/theme";
import { display, mono } from "../../components/marketing/kit/styles";

interface Props {
  onDemoClick?: () => void;
  /** Start with no bar (transparent, borderless) at the top of the page and
   * fade the blurred panel in on scroll. Only safe on pages whose top section
   * is dark (the home + scheduling heroes) — default off everywhere else. */
  transparentAtTop?: boolean;
}

// Product offerings — primary nav, in sales order.
const PRODUCT_LINKS = [
  { to: "/matcha-platform", label: "Full Platform" },
  // { to: '/matcha-work', label: 'Matcha Work' }, // beta — hidden until launch
  { to: "/matcha-scheduling", label: "Scheduling", isNew: true },
  // { to: "/matcha-ops", label: "Matcha Ops", isNew: true }, // hidden for now
  { to: "/matcha-lite", label: "Matcha Lite" },
  { to: "/matcha-compliance", label: "Compliance", isNew: true },
  // { to: "/matcha-brokers", label: "Brokers", isNew: true }, // hidden for now
  { to: "/services", label: "Consulting" },
];

function NewBadge() {
  return (
    <span
      className="absolute -top-2.5 left-1/2 -translate-x-1/2 px-[5px] rounded-[2px] font-semibold leading-[1.4] whitespace-nowrap"
      style={mono("7px", { letterSpacing: "0.12em", backgroundColor: BOARD.STAMP, color: BOARD.PAPER })}
    >
      New
    </span>
  );
}

// Content / non-offering — split into the Explore sub-nav.
const EXPLORE_LINKS = [
  { to: "/resources", label: "Resources" },
  { to: "/news", label: "News" },
];

const TEXT_COLOR = BOARD.INK;

export default function MarketingNav({
  onDemoClick,
  transparentAtTop = false,
}: Props) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [exploreOpen, setExploreOpen] = useState(false);
  const { pathname } = useLocation();

  const closeAll = () => {
    setMenuOpen(false);
    setExploreOpen(false);
  };

  // With transparentAtTop the blurred panel lives on its own layer and fades
  // in once the visitor scrolls — the hero opens with no chrome at all.
  const [scrolled, setScrolled] = useState(!transparentAtTop);
  useEffect(() => {
    if (!transparentAtTop) return;
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [transparentAtTop]);

  const panelVisible = scrolled || menuOpen;

  return (
    <>
      <nav className="fixed left-0 right-0 top-0 z-50" style={{ fontFamily: BODY }}>
        <div
          aria-hidden
          className="absolute inset-0 transition-opacity duration-500"
          style={{
            opacity: panelVisible ? 1 : 0,
            backgroundColor: hexA(BOARD.PAPER, 0.88),
            backdropFilter: "blur(14px) saturate(1.3)",
            WebkitBackdropFilter: "blur(14px) saturate(1.3)",
            borderBottom: `1px solid ${hexA(BOARD.INK, 0.1)}`,
          }}
        />
        <div className="relative max-w-[1440px] mx-auto flex items-center justify-between px-6 sm:px-10 h-16">
          <Link
            to="/"
            onClick={closeAll}
            className="group flex items-center gap-2.5"
          >
            {/* Leaf mark — pure CSS: one corner squared off turns the circle
                into a matcha leaf. Green lives here; the wordmark stays chalk. */}
            <span
              aria-hidden
              className="block w-[15px] h-[15px] shrink-0 transition-transform duration-500 ease-out group-hover:rotate-[135deg]"
              style={{
                background: `linear-gradient(135deg, ${BOARD.STAMP} 0%, ${STAMP} 100%)`,
                borderRadius: "50% 2px 50% 50%",
              }}
            />
            <span
              className="leading-none"
              style={{ ...display, fontWeight: 600, fontSize: 21, letterSpacing: "-0.03em", color: BOARD.INK }}
            >
              Matcha
            </span>
          </Link>

          <div className="hidden md:flex items-center gap-8">
            {PRODUCT_LINKS.map((link) => {
              const active = pathname === link.to;
              return (
                <Link
                  key={link.to}
                  to={link.to}
                  className={`group relative font-['JetBrains_Mono',ui-monospace,monospace] text-[10.5px] uppercase tracking-[0.1em] transition-colors duration-200 ${
                    active
                      ? "text-[#E9EDE5]"
                      : "text-[#E9EDE5]/70 hover:text-[#E9EDE5]"
                  }`}
                >
                  {link.label}
                  {link.isNew && <NewBadge />}
                  {/* hairline underline — grows in on hover, pinned on the
                      active route */}
                  <span
                    className={`pointer-events-none absolute left-0 -bottom-1.5 h-px w-full origin-left transition-transform duration-300 ${
                      active
                        ? "scale-x-100"
                        : "scale-x-0 group-hover:scale-x-100"
                    }`}
                    style={{ backgroundColor: BOARD.STAMP }}
                  />
                </Link>
              );
            })}

            {/* Explore sub-nav — Blog / Resources / News split out from offerings */}
            <div
              className="relative"
              onMouseEnter={() => setExploreOpen(true)}
              onMouseLeave={() => setExploreOpen(false)}
            >
              <button
                type="button"
                onClick={() => setExploreOpen((v) => !v)}
                className="inline-flex items-center gap-1 font-['JetBrains_Mono',ui-monospace,monospace] text-[10.5px] uppercase tracking-[0.1em] transition-colors duration-200 text-[#E9EDE5]/70 hover:text-[#E9EDE5]"
                aria-expanded={exploreOpen}
                aria-haspopup="true"
              >
                Explore
                <ChevronDown
                  className="w-3.5 h-3.5 transition-transform duration-200"
                  style={{ transform: exploreOpen ? "rotate(180deg)" : "none" }}
                />
              </button>

              {exploreOpen && (
                <div
                  className="absolute right-0 top-full pt-3"
                  // pt-3 keeps a hover bridge between trigger and panel
                >
                  <div
                    className="min-w-[160px] rounded-lg overflow-hidden py-1.5"
                    style={{
                      backgroundColor: BOARD.CARD,
                      border: `1px solid ${hexA(BOARD.INK, 0.1)}`,
                      boxShadow: "0 20px 40px -12px rgba(0,0,0,0.55)",
                    }}
                  >
                    {EXPLORE_LINKS.map((link) => (
                      <Link
                        key={link.to}
                        to={link.to}
                        onClick={closeAll}
                        className="block px-4 py-2.5 text-sm transition-colors hover:bg-white/[0.06]"
                        style={{ color: TEXT_COLOR }}
                      >
                        {link.label}
                      </Link>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="flex items-center gap-4">
            <Link
              to="/login"
              className="hidden md:inline text-[14px] font-medium transition-colors duration-200 text-[#E9EDE5]/70 hover:text-[#E9EDE5]"
            >
              Login
            </Link>
            <button
              onClick={onDemoClick}
              className="hidden sm:inline-flex items-center h-10 px-5 rounded-full text-[14px] font-medium cursor-pointer transition-colors duration-300 bg-[#F2F4EF] text-[#18211B] hover:bg-[#8FC46B]"
            >
              Request Demo
            </button>
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              className="md:hidden inline-flex items-center justify-center w-10 h-10 -mr-2"
              style={{ color: TEXT_COLOR }}
              aria-label={menuOpen ? "Close menu" : "Open menu"}
            >
              {menuOpen ? (
                <X className="w-5 h-5" />
              ) : (
                <Menu className="w-5 h-5" />
              )}
            </button>
          </div>
        </div>
      </nav>

      {menuOpen && (
        <div
          className="fixed inset-0 z-40 md:hidden overflow-y-auto"
          style={{ backgroundColor: BOARD.PAPER, fontFamily: BODY }}
        >
          <div className="pt-28 px-6 pb-12 flex flex-col gap-1">
            {PRODUCT_LINKS.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                onClick={closeAll}
                className="py-4 border-b"
                style={{
                  ...display,
                  fontSize: 28,
                  color: BOARD.INK,
                  borderColor: hexA(BOARD.INK, 0.12),
                }}
              >
                <span className="relative inline-block">
                  {link.label}
                  {link.isNew && <NewBadge />}
                </span>
              </Link>
            ))}

            {/* Explore sub-section */}
            <div
              className="mt-6 mb-2"
              style={mono("10.5px", { color: hexA(BOARD.INK, 0.5) })}
            >
              Explore
            </div>
            {EXPLORE_LINKS.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                onClick={closeAll}
                className="py-3 text-lg border-b"
                style={{
                  color: hexA(BOARD.INK, 0.85),
                  borderColor: hexA(BOARD.INK, 0.1),
                }}
              >
                {link.label}
              </Link>
            ))}

            <Link
              to="/login"
              onClick={closeAll}
              className="mt-6 py-3 text-lg"
              style={{ color: BOARD.INK }}
            >
              Login
            </Link>
            <button
              onClick={() => {
                closeAll();
                onDemoClick?.();
              }}
              className="mt-4 inline-flex items-center justify-center px-6 h-12 rounded-full text-base font-medium cursor-pointer"
              style={{
                backgroundColor: PAPER,
                color: INK,
              }}
            >
              Request a Demo
            </button>
          </div>
        </div>
      )}
    </>
  );
}
