// Four complete art directions, made of ordinary editable Studio frames.
// Contents occupies a spread so opening, essay and interview pairs face
// each other in the Studio's right-hand-cover pagination.
import type { EditorialCollection } from '../../model/collections'
import type { CharAttrs, Doc, ParaAttrs } from '../../model/types'
import { templateItems } from './applyTemplate'
import { BASE, type Template, type TItem } from './templates'

type Direction = {
  id: string; name: string; direction: string; description: string
  display: string; body: string; label: string; weight: number
  paper: string; ink: string; accent: string; picture: string; margin: number; title: string; deck: string
}
const DIRECTIONS: Direction[] = [
  { id: 'quiet-form', name: 'Quiet Form', direction: 'Restrained fashion editorial',
    description: 'Precise hairlines, generous white space and sculptural serif headlines. A measured rhythm for fashion and culture.',
    display: 'Bodoni Moda', body: 'Source Serif 4', label: 'Montserrat', weight: 500,
    paper: '#f7f6f2', ink: '#252522', accent: '#78766e', picture: '#c9c6bf', margin: 54,
    title: 'The quiet\nform', deck: 'Clothes, gestures and the space between.' },
  { id: 'off-register', name: 'Off Register', direction: 'Experimental art zine',
    description: 'Oversized grotesk type, acidic colour and an off-centre grid. Room for fragments, process and unexpected encounters.',
    display: 'Space Grotesk', body: 'IBM Plex Mono', label: 'IBM Plex Mono', weight: 700,
    paper: '#eee9df', ink: '#25231f', accent: '#e45232', picture: '#b6bc71', margin: 36,
    title: 'OFF\nREGISTER', deck: 'Notes on making something out of nothing.' },
  { id: 'still-light', name: 'Still Light', direction: 'Photographic monograph',
    description: 'Gallery-like margins, quiet captions and uninterrupted image sequences. Photographs set the pace.',
    display: 'EB Garamond', body: 'EB Garamond', label: 'Inter', weight: 400,
    paper: '#f5f3ee', ink: '#33332f', accent: '#686d68', picture: '#a9b2ad', margin: 66,
    title: 'Still Light', deck: 'A study of ordinary places, patiently observed.' },
  { id: 'maison', name: 'Maison', direction: 'Luxury lookbook',
    description: 'Warm ivory, deep ink and widely spaced small type. Deliberate proportions for objects, materials and collections.',
    display: 'Bodoni Moda', body: 'Lora', label: 'Montserrat', weight: 400,
    paper: '#f2eadf', ink: '#332d28', accent: '#8c7153', picture: '#c5b29c', margin: 72,
    title: 'MAISON', deck: 'A collection of considered things.' },
]

function pages(d: Direction): Template[] {
  const { w: W, h: H } = BASE, M = d.margin, C = W - 2 * M
  const zine = d.id === 'off-register', mono = d.id === 'still-light', luxury = d.id === 'maison'
  const part = (text: string, char: CharAttrs, para: ParaAttrs = {}) => ({ text, char, para })
  const text = (name: string, words: string, x: number, y: number, w: number, h: number,
    size = 11, role: ParaAttrs['role'] = 'p', align: ParaAttrs['align'] = 'l', extra: CharAttrs = {}): TItem => ({
    kind: 'text', name, x, y, w, h,
    parts: [part(words, { font: d.body, size, color: d.ink, ...extra }, { role, lead: size * 1.45, align })],
  })
  const heading = (name: string, words: string, x: number, y: number, w: number, h: number, size = 48): TItem =>
    text(name, words, x, y, w, h, size, 'h1', luxury ? 'c' : 'l', { font: d.display, wt: d.weight })
  const label = (name: string, words: string, x: number, y: number, w: number, align: ParaAttrs['align'] = 'l'): TItem =>
    text(name, words, x, y, w, 32, 8, 'caption', align, { font: d.label, track: zine ? 0 : 160, color: d.accent })
  const image = (name: string, x: number, y: number, w: number, h: number): TItem =>
    ({ kind: 'image', name, x, y, w, h, fill: d.picture })
  const rule = (y: number): TItem => ({ kind: 'line', name: 'Hairline', x: M, y, w: C, h: 0, stroke: { c: d.accent, w: zine ? 3 : 0.5 } })
  const page = (id: string, title: string, group: Template['group'], items: TItem[], n: number): Template => ({
    id: `${d.id}-${id}`, label: title, group, items: [
      { kind: 'rect', name: 'Paper', x: 0, y: 0, w: W, h: H, fill: d.paper }, ...items,
      label('Running title', `${d.name.toUpperCase()} / 01`, M, H - 38, C - 36),
      label('Folio', String(n).padStart(2, '0'), W - M - 28, H - 38, 28, 'r'),
    ],
  })
  const cover = mono ? [
    label('Edition', 'PHOTOGRAPHS / VOLUME ONE', M, 56, C),
    image('Cover photograph', M, 150, C, 400),
    heading('Masthead', d.title, M, 576, C, 110, 48),
    text('Cover subtitle', d.deck, M, 690, C, 42, 12),
  ] : zine ? [
    { kind: 'rect', name: 'Colour field', x: 0, y: 0, w: W, h: H, fill: d.accent } as TItem,
    heading('Masthead', d.title, M, 40, C, 280, 68),
    image('Cover artwork', 172, 330, W - 172, 336),
    label('Issue line', 'INDEPENDENT ART / ISSUE 001', M, 704, C),
  ] : luxury ? [
    label('Edition', 'COLLECTION / VOLUME 01', M, 52, C, 'c'),
    heading('Masthead', d.title, M, 104, C, 130, 52),
    image('Cover photograph', 132, 258, 348, 350),
    text('Cover subtitle', d.deck, M, 662, C, 48, 12, 'p', 'c'),
  ] : [
    label('Edition', 'AN INDEPENDENT FASHION JOURNAL / 01', M, 42, C),
    heading('Masthead', d.title, M, 94, C, 210, 58),
    image('Cover photograph', 210, 324, W - 210 - M, 346),
    text('Cover subtitle', d.deck, M, 690, C, 44, 12),
  ]
  return [
    page('cover', 'Cover', 'Covers', cover, 1),
    page('contents', 'Contents', 'More pages', [
      label('Section', 'IN THIS VOLUME', M, 54, C),
      heading('Contents title', zine ? 'INDEX /' : 'Contents', M, 112, C, 124, zine ? 54 : 44), rule(250),
      ...['Opening / A way of seeing', 'Photo essay / In the frame', 'Interview / In conversation', 'Credits / The people behind it'].flatMap((title, k) => [
        label(`Section number ${k}`, ['04—05', '06—07', '08—09', '10'][k], M, 290 + k * 102, 90),
        text(`Contents entry ${k}`, title, M + 100, 286 + k * 102, C - 100, 76, 16, 'h2', 'l', { font: d.display }),
      ]),
    ], 2),
    page('note', 'Editorial note', 'More pages', [
      image('Contents photograph', M, 66, C, 344),
      label('Section', 'A NOTE FROM THE EDITOR', M, 454, C),
      text('Editorial note', 'Every collection begins with a way of looking. This one is about attention: to a gesture, a surface, a place.\n\nReplace these words with your introduction. Let your images lead, and give the moments between them room to breathe.', M, 504, C, 194, 13),
    ], 3),
    page('opening-left', 'Opening spread · left', 'Openers', [
      label('Section', '01 / OPENING', M, 58, C),
      heading('Opening headline', zine ? 'WAYS\nOF SEEING' : 'A way\nof seeing', M, zine ? 156 : 214, C, 280, zine ? 56 : 52),
      rule(564), text('Opening introduction', d.deck + '\n\nAn opening thought, a fresh perspective. Introduce the story in a few considered lines.', M, 592, C, 132, 14),
    ], 4),
    page('opening-right', 'Opening spread · right', 'Openers', [
      image('Opening photograph', mono || luxury ? M : 0, mono || luxury ? 66 : 0,
        mono || luxury ? C : W, mono || luxury ? 594 : 706),
      label('Opening caption', '01 / A PLACE, A MOMENT, A NEW PERSPECTIVE', M, 710, C),
    ], 5),
    page('essay-left', 'Photo essay · left', 'Photo pages', [
      label('Section', '02 / PHOTO ESSAY', M, 54, C),
      image('Essay photograph 1', M, mono ? 194 : 128, C, mono ? 346 : 490),
      text('Essay caption 1', '01. Describe what we see, and what lies just beyond the frame.', M, 648, C, 60, 9, 'caption', 'l', { font: d.label }),
    ], 6),
    page('essay-right', 'Photo essay · right', 'Photo pages', [
      image('Essay photograph 2', M, 72, zine ? C * 0.72 : C, 280),
      image('Essay photograph 3', zine ? M + C * 0.28 : M, 386, zine ? C * 0.72 : C, 280),
      text('Essay caption 2', '02—03. A sequence, a contrast, a detail worth staying with.', M, 696, C, 40, 8, 'caption', 'l', { font: d.label }),
    ], 7),
    page('interview-left', 'Interview · portrait', 'More pages', [
      label('Section', '03 / IN CONVERSATION', M, 54, C),
      heading('Interview title', 'The art of\npaying attention', M, 112, C, 200, 38),
      image('Interview portrait', M, 350, C * (luxury ? 0.8 : 1), 330),
      label('Portrait caption', 'A CONVERSATION WITH [NAME]', M, 708, C),
    ], 8),
    page('interview-right', 'Interview · questions', 'More pages', [
      label('Interview byline', 'WORDS BY [NAME] / PHOTOGRAPHS BY [NAME]', M, 54, C), rule(108),
      { kind: 'text', name: 'Questions and answers', x: M, y: 150, w: C, h: 550, cols: zine ? 1 : 2, gutter: 24,
        parts: [
          ['Where does your work begin?', 'With something small. A shape, a conversation, a light that falls a certain way. I try to stay curious long enough to see where it leads.'],
          ['What do you return to?', 'The things that ask me to slow down. A material can teach you a great deal if you let it.'],
          ['What are you looking for now?', 'A little more space. Time to look again at what I thought I already knew.'],
        ].flatMap(([q, a]) => [
          part(q, { font: d.label, size: 9, wt: 600, color: d.ink }, { lead: 15, sb: 18 }),
          part(a, { font: d.body, size: 11, color: d.ink }, { lead: 17, sb: 6 }),
        ]),
      },
    ], 9),
    page('credits', 'Credits', 'More pages', [
      label('Section', 'THE PEOPLE BEHIND THIS VOLUME', M, 54, C),
      heading('Credits title', zine ? 'MADE BY /' : 'Colophon', M, 132, C, 128, zine ? 44 : 48), rule(288),
      ...['EDITOR / [NAME]', 'ART DIRECTION / [NAME]', 'PHOTOGRAPHY / [NAME]', 'WORDS / [NAME]', 'STYLING / [NAME]'].map((credit, k) =>
        label(`Credit ${k}`, credit, M, 330 + k * 54, C)),
      text('Publication note', 'Volume 01 / [Season, year]\nPublished independently.\n\nFor image permissions, contributors and acknowledgements, add your details here.', M, 632, C, 106, 10),
    ], 10),
  ]
}

export const COLLECTIONS: EditorialCollection[] = DIRECTIONS.map((d) => {
  let doc: Doc = {
    v: 1, size: { ...BASE }, facing: true, margins: { t: d.margin, b: d.margin, i: d.margin, o: d.margin },
    cols: { n: 2, g: 24 }, baseline: { start: d.margin, step: 12 }, grid: { step: 12 }, bleed: 0,
    units: 'in', paper: d.paper, pages: [], items: [], threads: [], guides: [], paywall_page: null,
  }
  const templates = pages(d)
  templates.forEach((t, index) => {
    const id = `p${index + 1}`
    doc = { ...doc, pages: [...doc.pages, { id }] }
    const built = templateItems(t, doc, id)
    doc = { ...doc, items: [...doc.items, ...built.items], threads: [...doc.threads, ...built.threads] }
  })
  return { id: d.id, name: d.name, direction: d.direction, description: d.description,
    fonts: [...new Set([d.display, d.body, d.label])].join(' · '), pages: templates.map((t) => t.label), doc }
})
