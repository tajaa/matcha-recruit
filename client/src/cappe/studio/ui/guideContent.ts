// What the Studio's guide says, a section at a time (`StudioGuide.tsx` shows
// it). It opens by itself the first time someone opens the Studio, and from
// Help → How the Studio works, the "?" in the top bar and the Picture
// Editor's "?". Keep it to what the Studio really does: when a tool, panel or
// key changes, change its section here. The shortcuts section is made from
// the commands themselves.

import type { LucideIcon } from 'lucide-react'
import {
  BookOpen, CaseSensitive, Columns2, FileStack, FileType, Image, Keyboard, LayoutGrid, LayoutTemplate, Link2, MousePointer2, MousePointerClick, Move, PanelsTopLeft,
  PersonStanding, Ruler, Save, Scissors, Shapes, SlidersHorizontal, Smartphone, Sparkles, Type, WandSparkles, WrapText, ZoomIn,
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
      'Starting a writer account? Name your magazine and choose an editorial design during setup. Your first ten-page draft opens here, with your name on the cover and empty picture frames. Browse the pages, replace the sample words and add your own photos. Nothing is public until you publish; choose a magazine plan when you are ready.',
      'Everything you change saves by itself a moment later, and ⌘Z undoes it.',
      'Use the contents on the left to jump to any part of the Studio. You can open this guide again from Help → How the Studio works, or the ? at the top right.',
    ],
  },
  {
    id: 'around', group: 'Start', icon: PanelsTopLeft, title: 'Find your way around',
    points: [
      'Top bar: the story’s name (click it for its settings: headline, kicker, dek, byline, topic and who can read it), Board (every page at once), Preview, and Publish.',
      'Menus: everything the Studio can do, with the key that does the same thing beside it.',
      'The side panel, at the far left: Templates, Elements, Text, Photos, Yours (your pictures) and Board (your mood boards). Click anything there to add it, or drag it onto a page.',
      'Tools, beside it: what a click or a drag on the page makes or does.',
      'The pages, in the middle, on a grey pasteboard you can park things on.',
      'The bar over what you select: its font, size and colour, a picture’s crop, a shape’s fill, lining things up, and lock, duplicate and delete. Right-click anything for the rest (see The bar and the right-click menu).',
      'Panels, down the right: Pages, Magazine identity, Object, Character and Paragraph, plus the Story Editor. Window shows and hides each.',
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
      'Open it with Ask in the top bar, Help → Ask the Studio…, or Window → Ask the Studio. With something selected, the ✦ on the bar over it (or Ask about this… when you right-click it) opens Ask about just that, the question already started.',
      'It knows this guide, every menu command, the fonts you can use and what is on the page in view: each frame’s place, size, type and colours. Select something first to ask about just that.',
      'To match a look you like: select the part of your page, then give Ask a picture of the look: drag a screenshot onto the panel, paste one (a screenshot taken to the clipboard works), or choose one. Ask “how can I make this look like this?”: the Studio also sends a picture of the part you selected (or the page in view) as it looks now, so the answer compares the two side by side. Both show above the answer. You can also name a style or a kind of magazine instead.',
      'Buttons under an answer open this guide at the right section or start what the answer describes. Ask never changes your page itself: you make each change, and ⌘Z undoes it. To have the changes made for you, switch to Merlin (below).',
      'Answers come from AI and can be wrong. Questions aren’t saved, and closing the Studio clears them.',
    ],
  },
  {
    id: 'merlin', group: 'Start', icon: WandSparkles, title: 'Design with Merlin',
    body: 'Merlin designs the page in view for you. Switch the bar under Ask the Studio from Ask to Merlin, say what you want (“make this feel like a fashion magazine”), or give it a picture of a look you like, and send.',
    points: [
      'Open it from the Merlin switch in Ask the Studio, Help → Design with Merlin…, or right-click: Design with Merlin… (on an empty part of the page, Design this page with Merlin…). Select something first and Merlin works on that, changing the rest of the page only as much as it needs.',
      'Merlin works in rounds, three at most: it looks at a picture of your page, makes its changes, then looks at the result and refines it. Each round says what it changed and why. Stop ends it after the step it is on; what it already changed stays.',
      'It moves, resizes and restyles frames (fonts, sizes, colours, spacing, columns), crops pictures in their frames, changes what is in front, hides things, changes the letter case of headings and captions, and adds shapes, rules and short labels. It never writes or rewrites your story’s words, never deletes anything and leaves locked frames alone.',
      'Everything Merlin does is one step: Undo Merlin, under its last round, or one ⌘Z takes the whole design back. If you change the page while it works, it stops there, and ⌘Z undoes your change first.',
      'It works on the page you were on when you sent it, even if you scroll away, and uses only fonts the Studio has.',
      'Merlin uses AI and can get things wrong: check what it did. You can ask it for 20 designs a day with a magazine plan (3 without). Requests aren’t saved.',
    ],
  },
  {
    id: 'add', group: 'Make', icon: Shapes, title: 'Add things from the side panel',
    body: 'The tabs at the far left hold what you can put on a page. Click a thing to add it to the middle of the page you’re on, or drag it to the spot you want. Click a tab again (or the « at its top) to fold the panel away.',
    points: [
      'Templates opens on Collections: coordinated designs from cover to credits (see Editorial collections below). Single pages has individual covers, openers, story pages, photo pages, contents, an interview, a list and a back page. On a blank page a single template lays out that page; otherwise it adds a new page after it. Sample photos appear only in previews. Fill its picture frames and type over its words. One undo removes the layout.',
      'Elements: shapes, lines, picture frames and colour blocks, and over 3,500 graphics: icons, stickers, badges, dividers and patterns, with Gummfit’s own picks first (From Gummfit). Search them all at the top; See all opens a whole group. A colour block, a whole-page frame or a pattern goes behind everything, edge to edge.',
      'Select a one-colour graphic (a shape, icon, badge, divider or pattern) and its Look, in the Object panel, changes its colour and whether it keeps its shape, stretches or repeats. Stickers keep their own colours.',
      'Text: a heading, a subheading or body text, the small styles (kicker, pull quote, caption), and font pairings set together in one frame. Double-click it on the page to type your own words.',
      'Photos: opens on free photos, modern stock you may use any way you like (CC0, from StockSnap.io, WordPress and Nappy), with Gummfit’s own picks above them; search, or tap a topic. The archives (Openverse, the Smithsonian, The Met, NASA) are a tap away, each picture credited. The first click puts it in your library too. Make an AI picture is here too.',
      'Yours: everything in your library. Upload a picture here, then click it, or drag it onto a picture frame to fill the frame.',
      'Board: your mood boards, beside the pages while you design. Choose a board at the top (↗ opens it in the dashboard, where you pin photos, screenshots, documents, notes and links). A library picture on it goes onto the page like one of Yours. A picture with a lock is private reference: click it, confirm you took it or may publish it, and it joins your library and lands on the page. Notes are there to read, and links and files open in a new tab.',
      'Insert in the menus opens each tab too.',
    ],
  },
  {
    id: 'identity', group: 'Make', icon: LayoutTemplate, title: 'A reusable magazine identity',
    body: 'Window → Magazine identity opens the magazine’s visual system: named paragraph and character styles, a palette, recurring parent layouts, page numbers and running headers. Each issue keeps its own editable copy.',
    points: [
      'Create identity starts with Body, Heading, Caption and Emphasis. Select text or a text frame, then Apply beside a named style. Paragraph styles set the whole paragraph’s type and spacing; character styles set selected words. The Character and Paragraph panels also offer the named styles.',
      'Click a style’s name to edit its font, size, colour and spacing. Every linked paragraph or word in these pages updates together, including text on parents. Local formatting overrides the shared style; reapply the named style to clear overrides. Link all caption paragraphs connects existing captions to the Caption style. Semantic roles alone do not link visual styles.',
      'The palette keeps named colours. Apply colour links selected text or frames; styles can also use a palette colour. Editing that swatch updates its linked uses. Choosing a custom colour in the normal panels makes that use local. Deleting a style or swatch keeps the current appearance.',
      'Parent layouts repeat ordinary frames behind a page’s local content. Save local page as new parent moves that page’s frames into a shared parent; pictures become empty frames. Choose that parent on other pages. Detach parent to edit this page makes a local copy. Update from local page changes the shared parent for every linked page. Text linked to another page must be unlinked before capture.',
      'Automatic page numbers follow the page order, starting at your chosen number. A running header repeats the magazine or section name. Skip the first page for a cover, hide both on an individual page, or give that page its own header. Reordering pages recalculates the numbers.',
      'Save for this magazine stores a reusable template. New paged issues start with a copy. Use saved magazine identity merges definitions by name into an existing issue; matching styles and colours update, and other definitions remain. Saving the template does not change published issues. Publish the edited issue through the usual save/update controls. A conflicting template save asks you to reload instead of overwriting another editor.',
    ],
  },
  {
    id: 'collections', group: 'Make', icon: BookOpen, title: 'Editorial collections',
    body: 'A complete editorial design, with typography, colour and spacing considered together across the whole publication. Open Templates → Collections to explore one.',
    points: [
      'Quiet Form is restrained fashion editorial; Off Register an experimental art zine; Still Light a photographic monograph; Maison a luxury lookbook. Each has ten editable pages: a cover, contents and editorial note, facing opening and photo-essay spreads, a two-page interview, and credits.',
      'Explore a collection to see every page and its type pairing. Use all pages starts a blank story with the collection, or inserts it after the spread in view. Blank pages are added when needed to keep the cover on the right and preserve your existing facing spreads. Your page size is used. Existing pages and their text stay in the story.',
      'The previews use illustrative sample photography and the Studio’s display and width cuts to show each design’s character. Sample photos are never added to your story or library. Your pages start with empty photo frames: fill them from Photos or Yours, and type over the sample words. The layouts are ordinary frames: move them, change the type, link text, and make the design your own. One ⌘Z undoes adding the whole collection. If the story would exceed its save limits, nothing is added.',
      'Save these pages stores your current pages as a named collection (up to 32 pages and 50 saved collections). It keeps type, spacing, words, shapes and guides. Photos become empty frames, and subscriber access settings stay with the source story. Saved collections are available across your account’s magazines.',
      'Open one of Your collections to preview and reuse it, or remove it from the library. Removing it never removes pages already added to a story.',
      'Saving and removing a collection keep running while you use another panel. Return to Collections to see the result. If a save loses its connection, retrying the same design completes that save without creating another copy.',
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
      'Object → Align lines one thing up with its page, or several with each other; Space evenly across or down puts even gaps between three or more. The bar’s Position button does the same.',
      'Lock (⌘L) stops something moving. Hide (⌘3) hides it, and Show all (⌥⌘3) brings back everything hidden on the page. ⌘D duplicates.',
    ],
  },
  {
    id: 'bar', group: 'Make', icon: MousePointerClick, title: 'The bar and the right-click menu',
    body: 'Select something and a bar appears just above it with what you change most. It moves out of the way while you drag, '
      + 'and the panels on the right still hold every exact setting.',
    points: [
      'Text: the font, its size (− and + step a point), colour, bold, italic, underline, alignment (click to go left, centre, right, justified) and Spacing for the letters and the lines. Select words to change just those; select the frame to change all of its words. While you type, the bar shows only these.',
      'Pictures: Replace, Edit (light, colour and filters), Cut out, Crop (fill or fit the frame, zoom, and the part to keep in view) and Across, which runs the picture over both pages of the spread. An empty frame shows Choose a picture.',
      'Shapes and lines: the fill (or No fill), and the border’s colour and weight; a rectangle’s corners too.',
      'Everything: Position (line it up with the page, or several things with each other, and space three or more evenly), Transparency, Lock, Duplicate, Delete, ✦ to ask how to make it look like a picture you like (see Ask the Studio), and ⋯ for the right-click menu. Something locked shows only Unlock.',
      'Right-click anything for Cut, Copy, Paste, Duplicate and Delete, what that kind of thing can do (type in it, replace or edit a picture, run it across the spread, link crops), Align, Arrange, Lock, Hide, Ask about this… and Design with Merlin…. Right-click an empty part of a page to paste, select everything on it, add or delete a page, open the templates or the issue board, or have Merlin design the page.',
      'In the menu, the arrow keys move through it, → opens Align or Arrange, ← goes back and Esc closes it.',
    ],
  },
  {
    id: 'guides', group: 'Make', icon: Ruler, title: 'Rulers, guides and snapping',
    points: [
      'Drag down from the top ruler, or right from the side ruler, to make a guide on the page you drop it on. Drag a guide back onto a ruler to remove it.',
      'The pink and violet lines are the page’s margins and columns. Set them in the Pages panel (Layout → Margins and columns).',
      'While you move or resize, things snap to guides, margins, columns, the grid and other things on the page, and the line they snap to lights up. Resizing with Alt held doesn’t snap.',
      'The View menu turns the rulers, guides, margins, baseline grid, document grid, gutter safety and snapping on and off.',
      'With facing pages, an amber striped strip either side of the spine is the gutter: the binding hides it, so keep words out of it. Pictures may run across.',
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
      'To see every page at once and put them in order, open the issue board (Board in the top bar, or ⌥⌘P).',
    ],
  },
  {
    id: 'board', group: 'Make', icon: LayoutGrid, title: 'The issue board',
    body: 'The board (Board in the top bar, Layout → Issue board, or ⌥⌘P) lays out every page at once, spread by spread, '
      + 'so you can judge how the issue reads from cover to back and put it in order.',
    points: [
      'Drag a page to move it; a green bar shows where it will land. Click to select a page, Shift-click for a run of them, ⌘-click to add one; drag any of them to move them all. ⌥← and ⌥→ move what is selected earlier or later, a spread at a time with facing pages.',
      'A page with a picture running across the spine moves with the page facing it, so the picture is never cut in two. Moving an odd number of pages turns the pages after them to the other side: the board says when.',
      'Stories: select a story’s first page and click Start a story here. Each story gets a name you can change, a grip to drag the whole story by, and arrows to move it before or after the next one. The ✕ takes the break away and its pages join the story before.',
      'The strip along the top is the issue’s rhythm: a block for each page, darker the heavier it looks. A good issue mixes a dramatic opening, quiet details, portraits and white space; long runs of the same shade read flat.',
      'Beats (on by default) label each page: Full-bleed picture, Picture, Portrait, Pictures, Quiet detail, Words, Words and pictures, Colour or White space.',
      'An amber ⚠ on a spread means words run into the gutter or cross the spine. A $ marks the pages for subscribers.',
      'Select a spread’s two pages and click Lay out the spread… for a paired layout: Across the spread, Clear of the spine, Diptych, Full bleed and a quiet page, or Portrait and detail. On a blank spread it lays out that spread; otherwise it comes in as a new spread after it, so nothing is covered.',
      'Double-click a page (or Open the page) to go to it in the editor. ⌘Z undoes on the board too; Esc or Back to the pages closes it.',
    ],
  },
  {
    id: 'text', group: 'Words', icon: Type, title: 'Type',
    points: [
      'With the Type tool (T), click a page or drag out a frame, then type. Click any text frame later to type in it again.',
      'Select words and use the bar over them for the font, size, colour, bold, italic, underline, alignment and spacing. The Character panel has all of it and more: the font (102 families, each with its weights and italics, 11 Gummfit cuts, or one of your own), size, leading, tracking, kerning, colour and underline.',
      'The Paragraph panel sets a paragraph’s alignment (left, centre, right or justified), indents, and space before and after.',
      'Paragraph styles (Body text, Headline, Heading, Subheading, Pull quote, Caption) also say what each paragraph is in the Text view readers get on phones.',
      'Write article bodies directly in the editor. Body text does not accept pasted or dropped text, on the page or in the Story Editor. Headlines, headings, pull quotes and captions still accept paste. Typing, spelling corrections and undo work as usual.',
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
    id: 'editorial', group: 'Words', icon: CaseSensitive, title: 'Editorial type',
    body: 'The finer controls a magazine’s type needs, in the Character and Paragraph panels.',
    points: [
      'Kerning: click between two letters and press ⌥→ to open the space or ⌥← to close it (with ⌘, five times as far). The Kerning field shows and sets it; with letters selected, ⌥← and ⌥→ change their tracking. A headline’s spacing is set pair by pair this way.',
      'Alternates and figures: select letters and turn on what their font offers, such as small caps, old-style or tabular figures, fractions, swashes, rare ligatures or a stylistic set. Select a single letter and try Alternates or a Set to swap in another drawing of it.',
      'Drop cap: in the Paragraph panel, choose how many lines deep (2 to 6) and how many letters (1 to 3). The cap grows to fill those lines and the lines beside it move over.',
      'Keep last lines and Keep first lines stop a column or frame break from leaving one or two of a paragraph’s lines alone at the top or foot of a column (widows and orphans). Last line words stops a paragraph ending on a single short word. They change where lines break, so the text may run a little longer.',
      'A style applied over letters keeps their kerning and alternates: those are choices made letter by letter.',
      'Gummfit cuts, at the end of the font list, are display cuts made for covers and headlines: Bodoni Moda Display, Fraunces Display and Playfair Poster (the hairline contrast of large type), Playfair Condensed Poster, and condensed or expanded widths of Noto Serif Display, Anybody, Archivo, League Gothic and Bricolage Grotesque. They’re the Studio’s own.',
    ],
  },
  {
    id: 'fonts', group: 'Words', icon: FileType, title: 'Your own fonts',
    body: 'Fonts you hold a licence for can be added to your magazine and set like any other. Character panel → Add your own font (or Manage).',
    points: [
      'Upload a TTF, OTF, WOFF or WOFF2 file (up to 10 MB) and give it a name. Add each weight and italic of a family under the same name, and they become one font with its styles.',
      'Tick that you hold a licence that lets you use it on a website: readers’ pages load it from Gummfit, as they load the Studio’s own fonts.',
      'The Studio keeps a cleaned copy of the file, never under its real name. Your fonts are this magazine’s, offered in Your fonts in every story of it.',
      'Remove takes a font off the list. Pages that already set it keep it, even after you add a replacement in the same weight and style: the replacement is for text you set from then on. Editorial collections and other magazines set its text in the default face instead.',
      'A font with only italics (or only upright styles) sets any text you give it in the style it has.',
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
    id: 'spreads', group: 'Pictures', icon: Columns2, title: 'Pictures across a spread',
    body: 'One picture can run over both pages of a spread, or show through several frames, with its crops kept lined up as if it were one print.',
    points: [
      'Select a picture frame on a page that faces another, and in the Object panel’s Across the spread click Across (out to the edges of both pages) or Clear of spine (two halves with the fold left white). Object → Run the picture across the spread and Split the picture clear of the spine do the same.',
      'Select two picture frames or more on one spread and click Link crops: they show one picture between them, as through windows. It works for a diptych too.',
      'Put a picture in any linked frame and it goes into all of them. Move or resize one frame to show a different part of the picture; move them all together and the picture moves with them. Change one’s focus or zoom and the picture moves in every frame.',
      'A selected frame’s linked partners show a dashed green outline. Unlink crops lets each frame go its own way, keeping what it shows. Turning a frame, or setting it to Fit or Stretch, unlinks it, and the frames still linked keep showing what they showed. A locked frame can’t be linked; lock one already in a group and it keeps its picture and crop while the others follow it.',
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
    id: 'wrap', group: 'Pictures', icon: WrapText, title: 'Text around pictures',
    body: 'Select a picture, shape or graphic and choose a Text wrap in the Object panel: text on the same page keeps away from it.',
    points: [
      'Around the box keeps text off the frame’s whole rectangle. Around the subject (for a picture with a cut-out) follows the person or thing in it, line by line, wherever the crop puts them.',
      'Distance sets how much room is kept around it. Each line takes the widest space left beside the picture at its height.',
      'Moving the picture sets the text again around it. Text in a frame that wraps something isn’t centred or spread vertically.',
    ],
  },
  {
    id: 'subject', group: 'Pictures', icon: PersonStanding, title: 'The subject in front of the lettering',
    body: 'For covers: the model stands in front of the masthead, with the letters behind them.',
    points: [
      'Put the photo behind the masthead, select it, and click Put the subject in front in the Object panel. If the photo has no cut-out yet, the Picture Editor opens at Cut out: click the person, then Done. A crop, turn or look made there goes on the photo behind as well, so the two still line up.',
      'The photo stays behind the text, and a frame showing its cut-out goes over the text at exactly the same place. The two are linked, so changing the photo’s focus or zoom moves both.',
      'Resize the new frame to choose which letters the subject covers: shrink it to the head, say, so they cross only the middle of the masthead.',
      'It’s clicked only on the subject, so the lettering around it stays easy to select and type in. Its credit is the photo’s, printed once; delete or hide the photo and the cut-out prints its own.',
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
  ['Right-click', 'The menu for what is under the pointer (arrows move through it, Esc closes it)'],
  ['\\ (Picture Editor)', 'Hold to see the picture before'],
  ['⌥← / ⌥→ (typing)', 'Kern the two letters at the caret (⌥⌘: ×5); with letters selected, their tracking'],
  ['⌥← / ⌥→ (issue board)', 'Move the selected pages a spread earlier or later'],
  ['Shift-click / ⌘-click (issue board)', 'Select a run of pages / add a page'],
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
