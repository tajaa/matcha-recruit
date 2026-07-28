/**
 * Light design system for /home-v2 — cream / matcha green / ink. A parallel
 * token set to pages/home/theme.ts (noir), NOT a variant of it: four other
 * marketing pages (`simpler-pages/*`) import the noir tokens directly, so this
 * file exists to keep this page's palette from leaking into (or depending on)
 * that one. Same inline-`style={{}}` hex convention — consumed directly by
 * SVG presentation attributes in places, so no CSS-variable indirection.
 */

export const CREAM = "#0A0A08";
export const CREAM_HI = "#161613";
export const INK = "#EFEAE0";
export const INK_SOFT = "#B3AEA3";
export const MATCHA = "#7E480A";
export const MATCHA_MID = "#C97A2E";
export const MATCHA_LT = "#E0A863";
export const MATCHA_WASH = "#211D16";
export const LINE = "rgba(239,234,224,0.14)";

export const DISPLAY = "'Space Grotesk', var(--font-display)";
export const SANS = "var(--font-sans)";
