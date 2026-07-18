// Thread chat theming. Project threads always use the dark editor theme;
// others respect the light/dark toggle (`lm`).
export type ThreadTheme = {
  border: string
  panelBg: string
  backArrow: string
  titleInput: string
  titleText: string
  editBtn: string
  badge: string
  modeOff: string
  jurisdBar: string
  jurisdLabel: string
  emptyText: string
  streamBg: string
  streamText: string
  textarea: string
  finText: string
}

export function buildThreadTheme(isProject: boolean, lm: boolean): ThreadTheme {
  return isProject ? {
    border:      'border-[#333]',
    panelBg:     'bg-[#1e1e1e]',
    backArrow:   'text-[#6a737d] hover:text-[#e8e8e8]',
    titleInput:  'bg-[#252526] text-[#e8e8e8] border border-[#555]',
    titleText:   'text-[#e8e8e8]',
    editBtn:     'text-[#6a737d] hover:text-[#e8e8e8]',
    badge:       'bg-[#ce9178]/20 text-[#ce9178]',
    modeOff:     'bg-[#2a2d2e] text-[#6a737d] hover:bg-[#333] hover:text-[#d4d4d4]',
    jurisdBar:   'bg-[#252526]',
    jurisdLabel: 'text-[#6a737d]',
    emptyText:   'text-[#6a737d]',
    streamBg:    'bg-[#252526] border border-[#333]',
    streamText:  'text-[#6a737d]',
    textarea:    'bg-[#1a1a1a] text-[#d4d4d4] border-[#555] focus:border-[#ce9178] placeholder-[#6a737d]',
    finText:     'text-[#6a737d]',
  } : {
    border:      lm ? 'border-zinc-200'  : 'border-zinc-800',
    panelBg:     lm ? 'bg-white'         : '',
    backArrow:   lm ? 'text-zinc-500 hover:text-zinc-900' : 'text-zinc-400 hover:text-white',
    titleInput:  lm ? 'bg-zinc-100 text-zinc-900 border border-zinc-300' : 'bg-zinc-800 text-white border border-zinc-600',
    titleText:   lm ? 'text-zinc-900'    : 'text-white',
    editBtn:     lm ? 'text-zinc-400 hover:text-zinc-900' : 'text-zinc-500 hover:text-white',
    badge:       lm ? 'bg-zinc-100 text-zinc-600' : 'bg-zinc-700 text-zinc-300',
    modeOff:     lm ? 'bg-zinc-100 text-zinc-500 hover:bg-zinc-200 hover:text-zinc-700' : 'bg-zinc-700 text-zinc-400 hover:bg-zinc-600 hover:text-zinc-200',
    jurisdBar:   lm ? 'bg-zinc-50/50'   : 'bg-zinc-900/50',
    jurisdLabel: lm ? 'text-zinc-400'   : 'text-zinc-500',
    emptyText:   lm ? 'text-zinc-400'   : 'text-zinc-500',
    streamBg:    lm ? 'bg-zinc-100/80 border border-zinc-200' : 'bg-zinc-800/60 border border-zinc-700/50',
    streamText:  lm ? 'text-zinc-500'   : 'text-zinc-400',
    textarea:    lm
      ? 'bg-zinc-100 text-zinc-900 border-zinc-300 focus:border-emerald-600 placeholder-zinc-400'
      : 'bg-zinc-800 text-white border-zinc-700 focus:border-emerald-600 placeholder-w-faint',
    finText:     lm ? 'text-zinc-500'   : 'text-zinc-500',
  }
}
