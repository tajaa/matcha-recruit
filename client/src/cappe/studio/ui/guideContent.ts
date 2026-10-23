// What the Studio's guide says, a section at a time (`StudioGuide.tsx` shows
// it). It opens by itself the first time someone opens the Studio, and from
// Help → How the Studio works, the "?" in the top bar and the Picture
// Editor's "?". Keep it to what the Studio really does: when a tool, panel or
// key changes, change its section here. The shortcuts section is made from
// the commands themselves.

import type { LucideIcon } from 'lucide-react'
import {
  FileStack, Image, Keyboard, LayoutTemplate, Link2, MousePointer2, Move, PanelsTopLeft, Ruler, Save,
  Scissors, Shapes, SlidersHorizontal, Smartphone, Sparkles, Type, ZoomIn,
} from 'lucide-react'

export type GuideSection = {
  id: string
  /** The part of the Studio it belongs to, shown in the contents. */
  group: string
  icon: LucideIcon
  title: string
  body?: string
  points?: string[]
}

export const GUIDE_SEEN_KEY = 'cappe-studio-guide-seen'

export const GUIDE: GuideSection[] = [
  {
    id: 'start', group: 'Start', icon: LayoutTemplate, title: 'A story made of pages',
    body: 'The Studio is where you design a story page by page, like a printed magazine. Words go in text frames, '
      + 'pictures in picture frames, and you place each one exactly where you want it. Readers see your pages just as '
      + 'you laid them out, scaled to their screen.',
    points: [
      'Everything you change saves by itself a moment later, and ⌘Z undoes it.',
      'Use the contents on the left to jump to any part of the Studio. You can open this guide again from Help → How the Studio works, or the ? at the top right.',
    ],
  },
  {
    id: 'around', group: 'Start', icon: PanelsTopLeft, title: 'Find your way around',
    points: [
      'Top bar: the story’s name (click it for its settings: headline, kicker, dek, byline, topic and who can read it), Preview, and Publish.',
      'Menus: everything the Studio can do, with the key that does the same thing beside it.',
      'The side panel, at the far left: Elements, Text, Photos and Yours (your pictures). Click anything there to add it, or drag it onto a page.',
      'Tools, beside it: what a click or a drag on the page makes or does.',
      'The pages, in the middle, on a grey pasteboard you can park things on.',
      'Panels, down the right: Pages, Object, Character and Paragraph, plus the Story Editor. Window shows and hides each.',
      'Status bar, along the bottom: the zoom, the page you’re on, what the tool in hand does, a red note when text doesn’t fit, and whether everything is saved.',
    ],
  },
  {
    id: 'view', group: 'Start', icon: ZoomIn, title: 'Move around the pages',
    points: [
      'Zoom in and out with ⌘= and ⌘−, or ⌘-scroll or pinch on a trackpad. The zoom menu in the status bar jumps to a size.',
      '⌘0 fits the page in the window, ⌥⌘0 the whole spread, and ⌘1 shows it at actual size.',
      'Scroll to move around. Hold Space and drag to move the pages with any tool, or use the Hand tool (H).',
      'The Zoom tool (Z): click to zoom in where you click, Alt-click to zoom out.',
    ],
  },
  {
    id: 'ask', group: 'Start', icon: Sparkles, title: 'Ask the Studio',
    body: 'Ask how to do something here, or how to make a page look the way you want, and get an answer for the page you’re on.',
    points: [
      'Open it with Ask in the top bar, Help → Ask the Studio…, or Window → Ask the Studio.',
      'It knows this guide, every menu command, the fonts you can use and what is on the page in view: each frame’s place, size, type and colours. Select something first to ask about just that.',
      'Ask “how can I make this look more like…” and name a style or a kind of magazine, or attach a picture of the look you’re after (or paste one into the question).',
      'Buttons under an answer open this guide at the right section or start what the answer describes. It never changes your page itself: you make each change, and ⌘Z undoes it.',
      'Answers come from AI and can be wrong. Questions aren’t saved, and closing the Studio clears them.',
    ],
  },
  {
    id: 'add', group: 'Make', icon: Shapes, title: 'Add things from the side panel',
    body: 'The tabs at the far left hold what you can put on a page. Click a thing to add it to the middle of the page you’re on, or drag it to the spot you want. Click a tab again (or the « at its top) to fold the panel away.',
    points: [
      'Elements: shapes, lines, picture frames and colour blocks. A colour block or a whole-page frame goes behind everything, edge to edge.',
      'Text: a heading, a subheading or body text, the small styles (kicker, pull quote, caption), and font pairings set together in one frame. Double-click it on the page to type your own words.',
      'Photos: free pictures from Openverse, the Smithsonian, The Met and NASA that a magazine may publish, each credited. The first click copies it into your library. Make an AI picture is here too.',
      'Yours: everything in your library. Upload a picture here, then click it, or drag it onto a picture frame to fill the frame.',
      'Insert in the menus opens each tab too.',
    ],
  },
  {
    id: 'tools', group: 'Make', icon: MousePointer2, title: 'The tools',
    body: 'Pick a tool down the left or press its letter. While a tool is in hand, the status bar says what it does; Esc puts it down and takes the Selection tool back.',
    points: [
      'Selection (V): select, move, resize and turn things.',
      'Type (T): click a page for a text frame as wide as the column, or drag one out. Click a text frame to type in it.',
      'Picture frame (F): opens the picture library to place a picture, or drag out an empty frame to fill later.',
      'Rectangle (M) and Ellipse (L): drag one out (Shift: a square or a circle), or click for a 2-inch one.',
      'Line (\\): drag on a page (Shift: straight or at 45°), or click for a 2-inch line.',
      'Hand (H) moves around the pages. Zoom (Z) zooms in where you click.',
    ],
  },
  {
    id: 'objects', group: 'Make', icon: Move, title: 'Select, move and shape',
    points: [
      'Click something to select it; Shift-click to add to the selection, or drag across empty page to select everything you touch.',
      'Drag to move it. Shift keeps it level or upright; Alt-drag moves a copy and leaves the original.',
      'Drag a handle to resize (Shift keeps its shape, Alt resizes from the middle). Drag the round handle above it to turn it (Shift: 15° at a time).',
      'The arrow keys nudge by a point, with Shift by ten.',
      'The Object panel has the exact position, size, turn and opacity, plus fill, stroke and corners. Its arrange buttons, or ⌘] and ⌘[, bring things forward and send them back.',
      'Lock (⌘L) stops something moving. Hide (⌘3) hides it, and Show all (⌥⌘3) brings back everything hidden on the page. ⌘D duplicates.',
    ],
  },
  {
    id: 'guides', group: 'Make', icon: Ruler, title: 'Rulers, guides and snapping',
    points: [
      'Drag down from the top ruler, or right from the side ruler, to make a guide on the page you drop it on. Drag a guide back onto a ruler to remove it.',
      'The pink and violet lines are the page’s margins and columns. Set them in the Pages panel (Layout → Margins and columns).',
      'While you move or resize, things snap to guides, margins, columns, the grid and other things on the page, and the line they snap to lights up. Resizing with Alt held doesn’t snap.',
      'The View menu turns the rulers, guides, margins, baseline grid, document grid and snapping on and off.',
      'Rulers and every measurement use the units you pick in the Pages panel: inches, centimetres, millimetres, points, picas or pixels.',
    ],
  },
  {
    id: 'pages', group: 'Make', icon: FileStack, title: 'Pages and the document',
    points: [
      'The Pages panel shows every page; click one to go to it. Its buttons add a page after the one you’re on (⇧⌘P), move it earlier or later, or delete it with what is on it.',
      'Layout → Add a spread adds two facing pages. With Facing pages on, pages pair up as spreads the way a magazine opens.',
      'Document: the page size (Letter, A4, Magazine, Tabloid, Square, Portrait 4:5 or your own), margins, columns and gutter, the baseline and document grids, bleed, units and the paper colour.',
      'For a subscribers’ story (story settings → Who can read it), pick here the first page that needs a subscription. Page 1 is always free, so everyone sees the opening.',
    ],
  },
  {
    id: 'text', group: 'Words', icon: Type, title: 'Type',
    points: [
      'With the Type tool (T), click a page or drag out a frame, then type. Click any text frame later to type in it again.',
      'Select words and use the Character panel: the font (95 faces, each with its weights and italics), size, leading, tracking, colour and underline.',
      'The Paragraph panel sets a paragraph’s alignment (left, centre, right or justified), indents, and space before and after.',
      'Paragraph styles (Body text, Headline, Heading, Subheading, Pull quote, Caption) also say what each paragraph is in the Text view readers get on phones.',
      'Select a text frame (not its words) to set its columns, gutter, inset and vertical alignment in the Object panel.',
      'The Story Editor (⌘Y) shows a frame’s text as plain lines, handy for long passages and checking spelling.',
    ],
  },
  {
    id: 'flow', group: 'Words', icon: Link2, title: 'Text that flows',
    body: 'A story can run through several frames, across columns and pages. Each text frame has a small box at its top left (where text comes in) and one at its bottom right (where it goes on).',
    points: [
      'Click a frame’s bottom-right box, then click another text frame: the text continues there. The status bar reminds you while you choose; Esc stops.',
      'A red + in that box, and “Some text doesn’t fit” in the status bar, mean there’s more text than room. Make the frame bigger or flow it into another one.',
      'Stop the text flowing on from here, in the Object panel, ends the chain at that frame.',
    ],
  },
  {
    id: 'pictures', group: 'Pictures', icon: Image, title: 'Pictures in frames',
    points: [
      'Place a picture with ⌘P or the Picture frame tool: choose one from your library, or upload one there. Double-click an empty frame to fill it.',
      'In the Object panel, Fit says how the picture sits in its frame: Fill covers the frame and trims what’s over, Fit shows all of it, and Stretch fills it exactly. Zoom and the focus sliders choose which part shows.',
      'Replace picture… swaps it for another. The caption is what readers see beside it in the Text view.',
      'Every picture’s credit prints by itself, from the library.',
    ],
  },
  {
    id: 'picture', group: 'Pictures', icon: SlidersHorizontal, title: 'Edit a picture',
    body: 'Double-click a picture on the page (or press ⇧⌘E, or use Edit picture… in the Object panel) to open the Picture Editor.',
    points: [
      'Looks, down the left, are ready-made filters. Each shows your picture with it; click one to try it.',
      'Adjust sets the light (exposure, contrast, highlights, shadows, whites, blacks), the colour (temperature, tint, vibrance, saturation, black and white), effects (clarity, sharpen, vignette, grain, fade) and split toning. A look sets these for you, and you can change them after.',
      'Crop: pick a shape (1:1, 4:5, 16:9…) or drag the box’s corners and sides; straighten with Angle, turn a quarter at a time, or flip.',
      'Hold Before (or the \\ key) to compare with the original. Undo and redo work here too, and Reset all starts over.',
      'Done saves the result as a new picture in your library and puts it in the frame. The original never changes, and opening the edit again brings back every setting.',
    ],
  },
  {
    id: 'cutout', group: 'Pictures', icon: Scissors, title: 'Cut something out',
    body: 'In the Picture Editor’s Cut out tab (or Cut out… in the Object panel), the Studio lifts something out of its background, right in your browser.',
    points: [
      'Click what to keep. Click more of it to add to the cut-out; Alt-click, or Take away, to remove a part.',
      'The checkerboard is what has been cut away: on the page, whatever is behind the picture shows through there.',
      'Feather softens the edge. Keep the background instead flips it, and Start over clears it.',
      'The first time, the Studio downloads its cut-out model (about 14 MB) and reads the picture for a few seconds; after that each click takes a moment.',
    ],
  },
  {
    id: 'save', group: 'Finish', icon: Save, title: 'Saving, versions and publishing',
    points: [
      'Changes save a moment after you make them; the status bar says Saved.',
      '⌘S keeps a version you can go back to. File → Versions… lists them and restores one.',
      'Preview shows the story as readers will get it, unsaved changes included.',
      'Publish puts it live. After that, your changes save to a working copy (“Changes not live yet”) until you click Update live story, so readers never see a half-finished page.',
      'If the story was saved somewhere else since you opened it, the Studio stops saving and asks you to reload, so nothing is overwritten.',
    ],
  },
  {
    id: 'readers', group: 'Finish', icon: Smartphone, title: 'What readers get',
    points: [
      'Your pages exactly as designed, scaled to the screen, turned with arrows or the keyboard.',
      'On a phone, one page at a time with pinch to zoom, and a Text view: the words and pictures in reading order, sized for a phone. It also feeds your emails, the feed and the app.',
      'Subscribers-only pages show as locked until a reader subscribes.',
    ],
  },
  {
    id: 'keys', group: 'Finish', icon: Keyboard, title: 'Keyboard shortcuts',
    body: 'The menus show these too. ⌘ is Ctrl on Windows.',
  },
]

/** Keys that aren't a menu command, for the shortcuts section. */
export const MORE_KEYS: [string, string][] = [
  ['Space + drag', 'Move around the pages'],
  ['⌘ + scroll', 'Zoom'],
  ['Arrows (⇧: ×10)', 'Nudge what is selected'],
  ['Esc', 'Put the tool down, then let go of the selection'],
  ['Alt + drag', 'Move a copy'],
  ['Double-click', 'Type in a text frame, edit a picture'],
  ['\\ (Picture Editor)', 'Hold to see the picture before'],
]

/** Whether this browser has seen the guide (storage can be off: then say yes, never nag). */
export function guideSeen(): boolean {
  try {
    return window.localStorage.getItem(GUIDE_SEEN_KEY) === '1'
  } catch {
    return true
  }
}

export function markGuideSeen(): void {
  try {
    window.localStorage.setItem(GUIDE_SEEN_KEY, '1')
  } catch {
    // Storage off: it opens again next time, which is harmless.
  }
}
