/**
 * Card colours as CSS variables that fall back to the NOIR values, so a page
 * can re-tone the four instruments without forking them. Home sets the
 * `--mk-*` variables to the marketing kit's palette (see HOME_CARD_TONES in
 * ProductCarousel.tsx); the product pages set nothing and render as before.
 */
export { DISPLAY } from "../theme";
export const ASH = "var(--mk-8F8B80, #8F8B80)";
export const BONE = "var(--mk-F5F2ED, #F5F2ED)";
export const LINE_D = "color-mix(in srgb, var(--mk-F5F2ED, #F5F2ED) 14%, transparent)";
