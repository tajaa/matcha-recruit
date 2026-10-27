// Ready-made pages for the side panel's Templates tab: covers, openers, body
// pages, photo pages, a quote, contents, an interview, a list and a back
// page. Each is drawn on a Letter page (612 × 792 pt) and fitted to the
// story's page size when it is used (`templateItems`). Picture frames are
// left empty, to fill from Photos or Yours; the words are there to type over.
// Every face is one the Studio has and every graphic one in the bank
// (templates.test.tsx holds both, and that the words fit their frames).

import type { CharAttrs, GraphicFit, ParaAttrs } from '../../model/types'

export const BASE = { w: 612, h: 792 }

type Part = { text: string; char: CharAttrs; para: ParaAttrs }
type Common = { x: number; y: number; w: number; h: number; rot?: number; opacity?: number; name?: string }
export type TItem =
  | Common & { kind: 'text'; parts?: Part[]; thread?: string; cols?: number; gutter?: number; inset?: number;
    valign?: 'top' | 'center' | 'bottom'; fill?: string | null }
  | Common & { kind: 'image'; fill?: string | null; radius?: number }
  | Common & { kind: 'rect'; fill: string | null; radius?: number; stroke?: { c: string; w: number } | null }
  | Common & { kind: 'ellipse'; fill: string | null }
  | Common & { kind: 'line'; stroke: { c: string; w: number } }
  | Common & { kind: 'graphic'; src: string; color: string | null; fit: GraphicFit }

export type Template = { id: string; label: string; group: 'Covers' | 'Openers' | 'Body pages' | 'Photo pages' | 'More pages'; items: TItem[] }

const W = BASE.w, H = BASE.h, M = 54
const INK = '#1a1a1a', PAPER = '#ffffff', CREAM = '#f3efe6', RUST = '#b4532a', TEAL = '#1f3a3d', FRAME = '#e3ddd3'
// Graphics from the bank (graphics_manifest.json), by sha.
export const GRAPHICS = {
  burst: '390e9c7f8b40cca4b7ffae9406410d4c0f0adfe20e5cfc926de32dc66dadd51b',
  quote: '037363558376b91f735be569bce0184de8f3698bba1d6f02a1ed3f73648b9a3e',
  sparkle: 'f3784307888ff3c628a95ac966f53810057aefbc5e190e3b79c68c98716c3dad',
  ornament: 'a51617bed0e275ea9a2a747d8e61aff8f0a8217c4ac620faaeb80ab50727d6c6',
  thickThin: 'df6c8cca68065135403aa5bb4b0f6a816f47ccab307d7d6e1ce30fbc03d074df',
}

const p = (text: string, char: CharAttrs, para: ParaAttrs = {}): Part => ({ text, char, para })
const kicker = (text: string, color = RUST, align: ParaAttrs['align'] = 'l') =>
  p(text, { font: 'Inter', wt: 700, size: 8.5, track: 220, color }, { align })
const body = (text: string): Part => p(text, {}, { role: 'p', lead: 14.5, fi: 12, sa: 0 })
const BODY = [
  'The boats leave before light. By the time the first café opens its shutters, the harbour is already half empty, and the gulls have moved on to the next pier. Nobody here sets an alarm; the tide does that for them.',
  'Marta has fished these waters for thirty-one years. She keeps a notebook of every morning: the wind, the swell, the colour of the sky over the point. “You learn to read it,” she says, “the way you read a face you love.”',
  'Write your story here. Type over these words and the text flows on through every linked frame. Add more pages from the Pages panel and link a frame on each to keep it running.',
  'By noon the boats are back and the market is loud with weighing and bargaining. The best of the catch goes to three restaurants on the front; the rest is sold by the kilo to anyone who asks the right way.',
]

export const TEMPLATES: Template[] = [
  {
    id: 'cover-photo', label: 'Cover, full photo', group: 'Covers', items: [
      { kind: 'image', x: 0, y: 0, w: W, h: H, fill: '#8d8478', name: 'Cover picture' },
      { kind: 'rect', x: 0, y: 0, w: W, h: 230, fill: '#000000', opacity: 25, name: 'Top shade' },
      { kind: 'text', x: 30, y: 34, w: W - 60, h: 104, name: 'Masthead',
        parts: [p('THE QUARTERLY', { font: 'Bodoni Moda Display', wt: 600, size: 58, track: -10, color: PAPER }, { align: 'c', lead: 62 })] },
      { kind: 'text', x: 30, y: 144, w: W - 60, h: 16, name: 'Issue line',
        parts: [kicker('ISSUE 01  ·  AUTUMN  ·  YOUR TOWN', PAPER, 'c')] },
      { kind: 'text', x: 40, y: 430, w: 230, h: 170, name: 'Cover lines', parts: [
        kicker('INSIDE', PAPER), p('The coast in October', { font: 'Playfair Display', wt: 700, size: 22, color: PAPER }, { lead: 25, sb: 4 }),
        p('Ten towns worth the drive', { font: 'Source Serif 4', it: true, size: 12, color: PAPER }, { lead: 16, sb: 2 }),
        p('Bread, by hand', { font: 'Playfair Display', wt: 700, size: 22, color: PAPER }, { lead: 25, sb: 14 }),
        p('A baker’s year in pictures', { font: 'Source Serif 4', it: true, size: 12, color: PAPER }, { lead: 16, sb: 2 }),
      ] },
      { kind: 'graphic', x: 462, y: 214, w: 110, h: 110, src: GRAPHICS.burst, color: '#c0262d', fit: 'contain', name: 'Badge' },
      { kind: 'text', x: 462, y: 214, w: 110, h: 110, valign: 'center', name: 'Badge words',
        parts: [p('FREE\nISSUE', { font: 'Anton', size: 20, color: PAPER }, { align: 'c', lead: 21 })] },
      { kind: 'text', x: 40, y: 620, w: W - 80, h: 140, name: 'Headline', parts: [
        p('Gem of the Bay', { font: 'Playfair Display', wt: 900, it: true, size: 60, color: PAPER }, { role: 'h1', lead: 62 }),
        p('A morning at the top of the tower, and the bells that keep the town’s time.', { font: 'Source Serif 4', it: true, size: 14, color: PAPER }, { lead: 19, sb: 6 }),
      ] },
    ],
  },
  {
    id: 'cover-classic', label: 'Cover, classic', group: 'Covers', items: [
      { kind: 'rect', x: 0, y: 0, w: W, h: H, fill: CREAM, name: 'Paper' },
      { kind: 'rect', x: 0, y: 0, w: W, h: 196, fill: TEAL, name: 'Band' },
      { kind: 'text', x: M, y: 40, w: W - 2 * M, h: 14, name: 'Issue line', parts: [kicker('NO. 04  ·  THE MAKERS ISSUE', '#cfe1dc', 'c')] },
      { kind: 'text', x: M, y: 58, w: W - 2 * M, h: 118, name: 'Masthead',
        parts: [p('Field Notes', { font: 'Fraunces Display', size: 72, color: CREAM }, { align: 'c', lead: 80 })] },
      { kind: 'image', x: M, y: 226, w: W - 2 * M, h: 410, fill: FRAME, name: 'Cover picture' },
      { kind: 'text', x: M, y: 656, w: W - 2 * M, h: 100, name: 'Headline', parts: [
        p('Making Things by Hand', { font: 'Libre Caslon Display', size: 38, color: TEAL }, { role: 'h1', align: 'c', lead: 42 }),
        p('Potters, printers and a boatbuilder on slow work in a fast town', { font: 'Source Serif 4', it: true, size: 12.5, color: INK }, { align: 'c', lead: 17, sb: 4 }),
      ] },
    ],
  },
  {
    id: 'opener-photo', label: 'Opener, photo on top', group: 'Openers', items: [
      { kind: 'image', x: 0, y: 0, w: W, h: 456, fill: '#8d8478', name: 'Opening picture' },
      { kind: 'text', x: M, y: 488, w: W - 2 * M, h: 250, name: 'Headline', parts: [
        kicker('FEATURE'),
        p('The Long Way Home', { font: 'Playfair Display', wt: 900, size: 54 }, { role: 'h1', lead: 56, sb: 6 }),
        p('A dek that pulls the reader in: who this is about, where it happens, and why it matters now, in a sentence or two.',
          { font: 'Source Serif 4', it: true, size: 15 }, { lead: 21, sb: 10 }),
        p('BY YOUR NAME  ·  PHOTOGRAPHS BY THEIR NAME', { font: 'Inter', wt: 600, size: 7.5, track: 150, color: '#52525b' }, { sb: 16 }),
      ] },
    ],
  },
  {
    id: 'opener-split', label: 'Opener, split', group: 'Openers', items: [
      { kind: 'image', x: 0, y: 0, w: 306, h: H, fill: '#8d8478', name: 'Opening picture' },
      { kind: 'text', x: 336, y: 250, w: 222, h: 440, name: 'Headline', parts: [
        kicker('TRAVEL'),
        p('Notes from a Small Island', { font: 'Playfair Display', wt: 800, size: 38 }, { role: 'h1', lead: 41, sb: 6 }),
        p('Three days, two ferries and one very patient lighthouse keeper.', { font: 'Source Serif 4', it: true, size: 14 }, { lead: 19, sb: 10 }),
        p('BY YOUR NAME', { font: 'Inter', wt: 600, size: 7.5, track: 150, color: '#52525b' }, { sb: 14 }),
      ] },
      { kind: 'graphic', x: 336, y: 216, w: 60, h: 6, src: GRAPHICS.thickThin, color: RUST, fit: 'stretch', name: 'Rule' },
    ],
  },
  {
    id: 'body-two', label: 'Story, two columns', group: 'Body pages', items: [
      { kind: 'text', x: M, y: M, w: W - 2 * M, h: 50, name: 'Heading',
        parts: [p('A heading for this part of the story', { font: 'Playfair Display', wt: 700, size: 26 }, { role: 'h2', lead: 30 })] },
      { kind: 'line', x: M, y: 112, w: W - 2 * M, h: 0, stroke: { c: INK, w: 1 }, name: 'Rule' },
      { kind: 'text', x: M, y: 128, w: 246, h: H - 128 - M, thread: 'body', name: 'Column 1', parts: BODY.map(body) },
      { kind: 'text', x: 312, y: 128, w: 246, h: H - 128 - M, thread: 'body', name: 'Column 2' },
    ],
  },
  {
    id: 'body-quote', label: 'Story with a pull quote', group: 'Body pages', items: [
      { kind: 'text', x: M, y: M, w: W - 2 * M, h: 340, thread: 'body', cols: 3, gutter: 14, name: 'Story', parts: [...BODY, ...BODY].map(body) },
      { kind: 'graphic', x: 246, y: 414, w: 120, h: 12, src: GRAPHICS.ornament, color: RUST, fit: 'stretch', name: 'Ornament' },
      { kind: 'text', x: 84, y: 438, w: 444, h: 110, name: 'Pull quote',
        parts: [p('“You learn to read the sea the way you read a face you love.”', { font: 'Playfair Condensed Poster', it: true, size: 26 }, { role: 'quote', align: 'c', lead: 32 })] },
      { kind: 'text', x: M, y: 572, w: W - 2 * M, h: H - 572 - M, thread: 'body', cols: 3, gutter: 14, name: 'Story, continued' },
    ],
  },
  {
    id: 'photo-full', label: 'Full-page photo', group: 'Photo pages', items: [
      { kind: 'image', x: 0, y: 0, w: W, h: H, fill: '#8d8478', name: 'Picture' },
      { kind: 'text', x: 36, y: H - 96, w: 300, h: 60, inset: 10, fill: PAPER, name: 'Caption', parts: [
        p('What the picture shows, and why it matters to the story. Credits print by themselves.', { font: 'Inter', size: 8, color: INK }, { role: 'caption', lead: 11 }),
      ] },
    ],
  },
  {
    id: 'photo-grid', label: 'Four photos', group: 'Photo pages', items: [
      ...[[M, M], [312, M], [M, 352], [312, 352]].flatMap(([x, y], k): TItem[] => [
        { kind: 'image', x, y, w: 246, h: 250, fill: FRAME, name: `Picture ${k + 1}` },
        { kind: 'text', x, y: y + 256, w: 246, h: 30, name: `Caption ${k + 1}`,
          parts: [p('A caption for this picture.', { font: 'Inter', size: 7.5, color: '#52525b' }, { role: 'caption', lead: 10 })] },
      ]),
      { kind: 'text', x: M, y: 660, w: W - 2 * M, h: 78, name: 'Title', parts: [
        p('Around the Harbour', { font: 'Playfair Display', wt: 800, size: 30 }, { role: 'h2', lead: 33 }),
        p('One morning, four corners of the waterfront.', { font: 'Source Serif 4', it: true, size: 12 }, { lead: 16, sb: 2 }),
      ] },
    ],
  },
  {
    id: 'quote', label: 'Big quote', group: 'More pages', items: [
      { kind: 'rect', x: 0, y: 0, w: W, h: H, fill: RUST, name: 'Colour' },
      { kind: 'graphic', x: 266, y: 190, w: 80, h: 80, src: GRAPHICS.quote, color: '#f5e1d3', fit: 'contain', name: 'Quote mark' },
      { kind: 'text', x: 72, y: 296, w: W - 144, h: 260, name: 'Quote', parts: [
        p('“The tide doesn’t wait for anyone, and neither do the boats.”', { font: 'Playfair Display', it: true, size: 38, color: PAPER }, { role: 'quote', align: 'c', lead: 46 }),
        p('— MARTA, WHO HAS FISHED HERE FOR 31 YEARS', { font: 'Inter', wt: 600, size: 8, track: 180, color: '#f5e1d3' }, { align: 'c', sb: 18 }),
      ] },
    ],
  },
  {
    id: 'contents', label: 'Contents', group: 'More pages', items: [
      { kind: 'text', x: M, y: M, w: W - 2 * M, h: 80, name: 'Title',
        parts: [p('Contents', { font: 'Playfair Display', wt: 900, size: 56 }, { role: 'h1', lead: 60 })] },
      { kind: 'graphic', x: M, y: 140, w: W - 2 * M, h: 10, src: GRAPHICS.thickThin, color: INK, fit: 'stretch', name: 'Rule' },
      { kind: 'text', x: M, y: 168, w: 300, h: 560, name: 'List', parts: [
        ['04', 'The Long Way Home', 'Thirty-one years on the water'], ['12', 'Bread, by Hand', 'A baker’s year in pictures'],
        ['20', 'Notes from a Small Island', 'Three days and two ferries'], ['28', 'In Conversation', 'Ana Ruiz on building boats'],
        ['34', 'Five Places', 'Where to watch the sun go down'],
      ].flatMap(([n, title, dek], k) => [
        p(n, { font: 'Inter', wt: 700, size: 10, color: RUST }, { sb: k ? 22 : 0 }),
        p(title, { font: 'Playfair Display', wt: 700, size: 20 }, { role: 'h3', lead: 24, sb: 2 }),
        p(dek, { font: 'Source Serif 4', it: true, size: 11 }, { lead: 15 }),
      ]) },
      { kind: 'image', x: 380, y: 168, w: 178, h: 236, fill: FRAME, name: 'Picture' },
      { kind: 'text', x: 380, y: 410, w: 178, h: 40, name: 'Caption',
        parts: [p('On the cover: the bell tower at first light.', { font: 'Inter', size: 7.5, color: '#52525b' }, { role: 'caption', lead: 10 })] },
    ],
  },
  {
    id: 'interview', label: 'Interview', group: 'More pages', items: [
      { kind: 'text', x: M, y: M, w: 344, h: 150, name: 'Headline', parts: [
        kicker('IN CONVERSATION'),
        p('Ana Ruiz on Building Boats', { font: 'Playfair Display', wt: 800, size: 34 }, { role: 'h1', lead: 37, sb: 6 }),
        p('She learned from her grandfather and now teaches twelve apprentices a year.', { font: 'Source Serif 4', it: true, size: 13 }, { lead: 18, sb: 8 }),
      ] },
      { kind: 'image', x: 418, y: M, w: 140, h: 176, fill: FRAME, name: 'Portrait' },
      { kind: 'line', x: M, y: 250, w: W - 2 * M, h: 0, stroke: { c: INK, w: 0.75 }, name: 'Rule' },
      { kind: 'text', x: M, y: 266, w: W - 2 * M, h: H - 266 - M, cols: 2, gutter: 18, name: 'Questions and answers', parts: [
        ['When did you build your first boat?', 'At fourteen, badly. It leaked from every seam, and I loved it more than anything I have made since.'],
        ['What do your apprentices find hardest?', 'Patience. Wood moves when it wants to, not when you want it to, and the sea notices every shortcut.'],
        ['Has the work changed?', 'The tools have. The questions haven’t: will it float, will it last, and will someone love it enough to look after it.'],
        ['Type your next question here', 'And the answer under it. Bold questions, plain answers: the styles are already set.'],
      ].flatMap(([q, a]) => [
        p(q, { font: 'Inter', wt: 700, size: 9.5 }, { lead: 13.5, sb: 10 }),
        p(a, {}, { role: 'p', lead: 14.5, sb: 3 }),
      ]) },
    ],
  },
  {
    id: 'list', label: 'Top five list', group: 'More pages', items: [
      { kind: 'text', x: M, y: M, w: W - 2 * M, h: 96, name: 'Title', parts: [
        p('Five Places to Watch the Sun Go Down', { font: 'Playfair Display', wt: 800, size: 32 }, { role: 'h1', lead: 35 }),
      ] },
      ...[0, 1, 2, 3, 4].flatMap((k): TItem[] => {
        const y = 168 + k * 114
        return [
          { kind: 'text', x: M, y, w: 46, h: 64, name: `Number ${k + 1}`,
            parts: [p(String(k + 1), { font: 'Anton', size: 40, color: RUST }, { lead: 42 })] },
          { kind: 'text', x: 108, y, w: 292, h: 100, name: `Place ${k + 1}`, parts: [
            p(['The lighthouse steps', 'Point Reyes beach', 'The old ferry pier', 'Hilltop cemetery', 'Your favourite spot'][k],
              { font: 'Playfair Display', wt: 700, size: 17 }, { role: 'h3', lead: 21 }),
            p('Why it’s worth the walk, when to get there, and where to stand.', { font: 'Source Serif 4', size: 10.5 }, { lead: 14.5, sb: 3 }),
          ] },
          { kind: 'image', x: 418, y, w: 140, h: 96, fill: FRAME, radius: 4, name: `Picture ${k + 1}` },
        ]
      }),
    ],
  },
  {
    id: 'back-subscribe', label: 'Back page, subscribe', group: 'More pages', items: [
      { kind: 'rect', x: 0, y: 0, w: W, h: H, fill: TEAL, name: 'Colour' },
      { kind: 'graphic', x: 276, y: 236, w: 60, h: 60, src: GRAPHICS.sparkle, color: '#e0b24c', fit: 'stretch', name: 'Sparkle' },
      { kind: 'text', x: 72, y: 320, w: W - 144, h: 230, name: 'Call to subscribe', parts: [
        p('Read every issue', { font: 'DM Serif Display', size: 56, color: CREAM }, { role: 'h1', align: 'c', lead: 58 }),
        p('New stories each month, straight to your inbox. Subscribe on our site.', { font: 'Source Serif 4', it: true, size: 15, color: CREAM }, { align: 'c', lead: 21, sb: 12 }),
        p('YOURMAGAZINE.GUMMFIT.COM', { font: 'Inter', wt: 700, size: 10, track: 200, color: '#e0b24c' }, { align: 'c', sb: 20 }),
      ] },
    ],
  },
]
