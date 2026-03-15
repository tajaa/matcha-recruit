/**
 * Shared design tokens used across pages (Dashboard, Compliance, etc.).
 * Each page spreads the base and adds page-specific tokens.
 */

// ─── light base ─────────────────────────────────────────────────────────────

export const baseLT = {
  // page surface
  pageBg: 'bg-stone-200',
  pageText: 'text-zinc-900',
  pageMuted: 'text-stone-500',
  pageFaint: 'text-stone-400',
  pageDim: 'text-stone-600',
  pageBorder: 'border-stone-200',
  pageBtnPrimary: 'bg-zinc-900 text-zinc-50 hover:bg-zinc-800',
  pageLinkHover: 'hover:text-zinc-900',

  // cards
  card: 'bg-stone-100 rounded-xl',
  cardBg: 'bg-stone-100',
  cardHeader: 'border-b border-stone-200',
  innerEl: 'bg-stone-200 rounded-lg',
  innerHover: 'bg-stone-200 rounded-lg hover:bg-stone-300',

  // text
  textMain: 'text-zinc-900',
  textMuted: 'text-stone-500',
  textFaint: 'text-stone-400',
  textDim: 'text-stone-600',

  // structure
  border: 'border-stone-200',
  divide: 'divide-stone-200',
  rowHover: 'hover:bg-stone-50',
  icon: 'text-stone-400',
  arrow: 'text-stone-400 group-hover:text-zinc-900',
  label: 'text-xs text-stone-500 font-semibold',
  footerBg: 'border-t border-stone-200 bg-stone-200',
  footerLink: 'text-stone-500 hover:text-zinc-900',

  // controls
  btnPrimary: 'bg-zinc-900 text-zinc-50 hover:bg-zinc-800',
  btnSecondary: 'border border-stone-300 hover:border-stone-400 text-stone-600 hover:text-zinc-900',
  btnGhost: 'text-stone-500 hover:text-zinc-900',
  spinner: 'border-stone-300 border-t-zinc-900',
  input: 'bg-white border border-stone-300 text-zinc-900 rounded-xl placeholder:text-stone-400 focus:border-stone-400',
  select: 'bg-white border border-stone-300 rounded-xl text-zinc-900 focus:border-stone-400',

  // status
  statusOk: 'text-emerald-600',
  statusWarn: 'text-amber-600',
  statusErr: 'text-red-600',
  linkify: 'text-emerald-600 hover:text-emerald-700 underline',
  linkHover: 'hover:text-zinc-900',

  // tabs
  tabActive: 'text-zinc-900',
  tabInactive: 'text-stone-400 hover:text-stone-600',
  tabIndicator: 'bg-zinc-900',

  // semantic badges
  badgeNew: 'bg-emerald-50 text-emerald-600 border-emerald-200',
  badgeUpdated: 'bg-amber-50 text-amber-600 border-amber-200',
  badgeNominal: 'bg-stone-50 text-stone-400 border-stone-200',
  badgeBlue: 'bg-blue-50 text-blue-600 border-blue-200',
  badgeRed: 'bg-red-50 text-red-600 border-red-200',
  badgeAmber: 'bg-amber-50 text-amber-600 border-amber-200',
  badgeEmerald: 'bg-emerald-50 text-emerald-600 border-emerald-200',

  // modal
  modalBg: 'bg-stone-100 rounded-lg',
  closeBtnCls: 'text-stone-400 hover:text-zinc-900 transition-colors',
  cancelBtn: 'bg-transparent border border-stone-300 text-stone-500 hover:text-zinc-900 hover:bg-stone-200',
} as const;

// ─── dark base ──────────────────────────────────────────────────────────────

export const baseDK = {
  // page surface
  pageBg: 'bg-zinc-950',
  pageText: 'text-zinc-100',
  pageMuted: 'text-zinc-500',
  pageFaint: 'text-zinc-600',
  pageDim: 'text-zinc-400',
  pageBorder: 'border-white/10',
  pageBtnPrimary: 'bg-white text-black hover:bg-zinc-100',
  pageLinkHover: 'hover:text-white',

  // cards
  card: 'bg-zinc-900/50 border border-white/10 rounded-xl',
  cardBg: 'bg-zinc-900',
  cardHeader: 'border-b border-white/10',
  innerEl: 'bg-zinc-800 rounded-lg',
  innerHover: 'bg-zinc-800 rounded-lg hover:bg-zinc-700',

  // text
  textMain: 'text-zinc-100',
  textMuted: 'text-zinc-500',
  textFaint: 'text-zinc-600',
  textDim: 'text-zinc-400',

  // structure
  border: 'border-white/10',
  divide: 'divide-white/10',
  rowHover: 'hover:bg-white/5',
  icon: 'text-zinc-600',
  arrow: 'text-zinc-600 group-hover:text-zinc-100',
  label: 'text-xs text-zinc-500 font-semibold',
  footerBg: 'border-t border-white/10 bg-white/5',
  footerLink: 'text-zinc-500 hover:text-zinc-100',

  // controls
  btnPrimary: 'bg-zinc-700 text-zinc-100 hover:bg-zinc-600',
  btnSecondary: 'border border-white/10 hover:border-white/20 text-zinc-500 hover:text-zinc-100',
  btnGhost: 'text-zinc-500 hover:text-zinc-100',
  spinner: 'border-zinc-800 border-t-zinc-100',
  input: 'bg-zinc-900 border border-white/10 text-zinc-100 rounded-xl placeholder:text-zinc-600 focus:border-white/20',
  select: 'bg-zinc-900 border border-white/10 rounded-xl text-zinc-100 focus:border-white/20',

  // status
  statusOk: 'text-emerald-400',
  statusWarn: 'text-amber-400',
  statusErr: 'text-red-400',
  linkify: 'text-emerald-400 hover:text-emerald-300 underline',
  linkHover: 'hover:text-white',

  // tabs
  tabActive: 'text-zinc-100',
  tabInactive: 'text-zinc-600 hover:text-zinc-400',
  tabIndicator: 'bg-white',

  // semantic badges
  badgeNew: 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20',
  badgeUpdated: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  badgeNominal: 'bg-white/5 text-zinc-600 border-white/5',
  badgeBlue: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  badgeRed: 'bg-red-500/10 text-red-400 border-red-500/20',
  badgeAmber: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  badgeEmerald: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',

  // modal
  modalBg: 'bg-zinc-900 border border-white/10 rounded-lg',
  closeBtnCls: 'text-zinc-500 hover:text-zinc-100 transition-colors',
  cancelBtn: 'bg-transparent border border-white/10 text-zinc-500 hover:text-white hover:bg-white/5',
} as const;

export type BaseTheme = typeof baseLT;
