// Thread chat theming — built entirely on the werk `w-*` tokens
// (client/src/index.css). Values are static: the thread's local light/dark
// toggle (`lm` in useThreadController.ts) is expressed by adding the
// `.mw-light` class to the chat pane root (MatchaWorkThread.tsx), which
// repaints every `w-*` CSS var — no per-key light/dark fork needed here.
// Project threads used to get a separate VS Code-styled palette; that's
// gone (project identity is carried by the task badge + ProjectPanel +
// Add-to-Project affordance instead), so `buildThreadTheme` takes no
// arguments and this file has one theme, not three.
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
}

export function buildThreadTheme(): ThreadTheme {
  return {
    border:      'border-w-line',
    panelBg:     'bg-w-bg',
    backArrow:   'text-w-dim hover:text-w-text',
    titleInput:  'bg-w-surface2 text-w-text border border-w-line',
    titleText:   'text-w-text',
    editBtn:     'text-w-dim hover:text-w-text',
    badge:       'bg-w-surface2 text-w-dim',
    modeOff:     'bg-w-surface2 text-w-dim hover:bg-w-line hover:text-w-text',
    jurisdBar:   'bg-w-surface/50',
    jurisdLabel: 'text-w-faint',
    emptyText:   'text-w-faint',
    streamBg:    'bg-w-surface border border-w-line',
    streamText:  'text-w-dim',
    textarea:    'bg-w-surface2 text-w-text border-w-line focus:border-w-accent placeholder-w-faint',
  }
}
