import { useEffect, useMemo, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  AlertCircle, Check, Eye, FolderOpen, History, Image, Loader2, Lock, Maximize2, Minimize2,
  MousePointerClick, Paperclip, Pencil, Plus, Search, Slash, Sparkles, Trash2, Wand2, X,
} from 'lucide-react'
import { AssetLibrary } from './AssetLibrary'
import { usePremium } from './DesignPrimitives'
import {
  MERLIN_MAX_WIDTH,
  MERLIN_MIN_WIDTH,
  MERLIN_TIERS,
  type MerlinStep,
  type MerlinTierChoice,
  type useMerlin,
} from './useMerlin'

/** Markdown, restyled for a 320-560px dark chat column. Merlin's prose is short
 *  but does use lists and inline code (field paths, color tokens), which read as
 *  literal asterisks and backticks when rendered raw. */
function Markdown({ children }: { children: string }) {
  return (
    <div className="space-y-1.5 [&_a]:text-emerald-400 [&_a]:underline [&_code]:rounded [&_code]:bg-black/30 [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-[11px] [&_li]:ml-4 [&_li]:list-disc [&_strong]:font-semibold">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </div>
  )
}

const STEP_ICONS = {
  ops: Wand2,
  screenshot: Eye,
  inspect: Search,
  critique: Eye,
  image: Image,
} as const

/** A generated image's "Apply to…" menu — re-target the SAME image onto a
 *  different field or a section background than wherever the model happened
 *  to place it. Reuses `merlin.getImageTargets`/`applyImageTo`, so this is a
 *  thin picker over the same apply path any chat-driven placement uses (one
 *  undo step, same result chips). */
function ApplyImageMenu({ url, merlin, premium }: { url: string; merlin: ReturnType<typeof useMerlin>; premium: boolean }) {
  const [open, setOpen] = useState(false)
  const boxRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    window.addEventListener('mousedown', onDown)
    return () => window.removeEventListener('mousedown', onDown)
  }, [open])

  const targets = open ? merlin.getImageTargets(premium) : []

  return (
    <div ref={boxRef} className="relative mt-1 inline-block">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 rounded px-1 py-0.5 text-[10px] font-medium text-emerald-400 hover:bg-zinc-800 hover:text-emerald-300"
      >
        <Wand2 className="h-2.5 w-2.5" /> Apply to…
      </button>
      {open && (
        <div className="absolute left-0 z-20 mt-1 max-h-64 w-56 overflow-y-auto rounded-lg border border-zinc-700 bg-zinc-900 p-1 shadow-xl">
          {targets.length === 0 && (
            <p className="p-2 text-[11px] text-zinc-500">No sections on this page yet.</p>
          )}
          {targets.map((t) => (
            <div key={t.blockId} className="mb-1 last:mb-0">
              <p className="px-2 pt-1 text-[10px] font-semibold uppercase tracking-wide text-zinc-500">{t.blockLabel}</p>
              {t.fields.map((f) => (
                <button
                  key={f.field}
                  onClick={() => { merlin.applyImageTo(url, { block: t.blockId, field: f.field }); setOpen(false) }}
                  className="block w-full rounded px-2 py-1 text-left text-xs text-zinc-200 hover:bg-zinc-800"
                >
                  → {f.label}
                </button>
              ))}
              {t.canBackground && (
                <button
                  onClick={() => { merlin.applyImageTo(url, { block: t.blockId, background: true }); setOpen(false) }}
                  className="block w-full rounded px-2 py-1 text-left text-xs text-zinc-200 hover:bg-zinc-800"
                >
                  → Background
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/** The agent loop's trace for a turn: what it applied, what it rendered, what
 *  it looked at. This is the visible difference between Merlin guessing and
 *  Merlin checking its own work, so it's shown rather than hidden behind a
 *  toggle — but compactly, above the reply it explains.
 *
 *  `merlin`/`premium` are omitted for the LIVE trail (a turn still in
 *  flight) — applying mid-turn would race the turn's own pending ops. */
function StepTrail({ steps, live, merlin, premium }: {
  steps: MerlinStep[]
  live?: boolean
  merlin?: ReturnType<typeof useMerlin>
  premium?: boolean
}) {
  if (!steps.length) return null
  return (
    <div className="mb-1.5 space-y-1 border-l border-zinc-700/70 pl-2">
      {steps.map((s, i) => {
        const Icon = STEP_ICONS[s.kind] ?? Wand2
        const last = live && i === steps.length - 1
        return (
          <div key={i} className="flex items-start gap-1.5 text-[11px] text-zinc-500">
            <Icon className={`mt-[2px] h-3 w-3 shrink-0 ${last ? 'text-emerald-400' : ''}`} />
            <div className="min-w-0">
              <span className={last ? 'text-zinc-300' : ''}>{s.label}</span>
              {s.image_url && (
                <>
                  <a
                    href={s.image_url}
                    target="_blank"
                    rel="noreferrer"
                    className={`mt-1 block ${s.kind === 'image' ? 'cursor-grab active:cursor-grabbing' : ''}`}
                    draggable={s.kind === 'image'}
                    onDragStart={s.kind === 'image' ? (e) => {
                      e.dataTransfer.setData('text/uri-list', s.image_url as string)
                      e.dataTransfer.setData('text/plain', s.image_url as string)
                      e.dataTransfer.effectAllowed = 'copy'
                    } : undefined}
                    title={s.kind === 'image' ? 'Drag onto a section to set as its background' : undefined}
                  >
                    <img
                      src={s.image_url}
                      alt="Rendered preview Merlin reviewed"
                      className="max-h-28 w-full rounded border border-zinc-700 object-cover object-top"
                    />
                  </a>
                  {!live && s.kind === 'image' && merlin && (
                    <ApplyImageMenu url={s.image_url} merlin={merlin} premium={!!premium} />
                  )}
                </>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

/** Chats tab body — full conversation history, always visible (replaces the
 *  old header dropdown, which hid older threads behind a small clock icon).
 *  Picking one opens it and hands control back to the caller (switch to the
 *  Merlin tab so the reopened thread is actually visible). */
function ChatsTab({ merlin, onOpen }: { merlin: ReturnType<typeof useMerlin>; onOpen: () => void }) {
  const { conversations, conversationId, openConversation, newConversation, renameConversation, deleteConversation } = merlin
  const [renaming, setRenaming] = useState<string | null>(null)
  const [draft, setDraft] = useState('')

  return (
    <div className="flex-1 overflow-y-auto p-2">
      <button
        onClick={() => { newConversation(); onOpen() }}
        className="mb-1 flex w-full items-center gap-1.5 rounded px-2 py-1.5 text-left text-xs text-emerald-400 hover:bg-zinc-800"
      >
        <Plus className="h-3.5 w-3.5" /> New conversation
      </button>
      {conversations.length === 0 && (
        <p className="px-2 py-4 text-center text-[11px] text-zinc-500">No past conversations on this page yet.</p>
      )}
      {conversations.length > 0 && <div className="my-1 border-t border-zinc-800" />}
      {conversations.map((c) => (
        <div key={c.id} className="group flex items-center gap-1 rounded px-1 hover:bg-zinc-800">
          {renaming === c.id ? (
            <input
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onBlur={() => { void renameConversation(c.id, draft); setRenaming(null) }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') { void renameConversation(c.id, draft); setRenaming(null) }
                if (e.key === 'Escape') { e.stopPropagation(); setRenaming(null) }
              }}
              className="min-w-0 flex-1 rounded border border-zinc-700 bg-zinc-950 px-1.5 py-1 text-xs text-zinc-100 outline-none focus:border-emerald-500"
            />
          ) : (
            <>
              <button
                onClick={() => { void openConversation(c.id); onOpen() }}
                className={`min-w-0 flex-1 truncate py-1.5 text-left text-xs ${c.id === conversationId ? 'font-medium text-emerald-300' : 'text-zinc-300'}`}
              >
                {c.title}
              </button>
              <button
                onClick={() => { setRenaming(c.id); setDraft(c.title) }}
                className="shrink-0 p-1 text-zinc-600 opacity-0 hover:text-zinc-200 group-hover:opacity-100"
                title="Rename"
              >
                <Pencil className="h-3 w-3" />
              </button>
              <button
                onClick={() => void deleteConversation(c.id)}
                className="shrink-0 p-1 text-zinc-600 opacity-0 hover:text-red-400 group-hover:opacity-100"
                title="Delete"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </>
          )}
        </div>
      ))}
    </div>
  )
}

/** Item shape shared by the slash-command list and every submenu it opens
 *  (add-section's presets+blocks, theme's presets) — one keyboard/click
 *  handler drives whichever list is currently showing. */
type MenuItem = { key: string; title: string; sub?: string; onPick: () => void }

type SlashAction =
  | { kind: 'prefill'; text: string }
  | { kind: 'send'; text: string }
  | { kind: 'submenu'; submenu: 'add-section' | 'theme' }
  | { kind: 'wizard' }

type SlashCommand = { id: string; label: string; hint: string; action: SlashAction }

// Static top-level commands. `/add-section` and `/theme` open a second list
// built from the live schema (server registries — sections/presets a hand-
// written list would drift from); the rest just prefill or send.
const SLASH_COMMANDS: SlashCommand[] = [
  {
    id: 'add-section', label: '/add-section', hint: 'Add a section — contact, about, blog…',
    action: { kind: 'submenu', submenu: 'add-section' },
  },
  {
    id: 'generate-image', label: '/generate-image', hint: 'Generate an AI image for a section',
    action: { kind: 'wizard' },
  },
  {
    id: 'restyle', label: '/restyle', hint: 'Restyle the selected section',
    action: { kind: 'prefill', text: 'Restyle this section to look ' },
  },
  {
    id: 'theme', label: '/theme', hint: 'Switch to a different theme preset',
    action: { kind: 'submenu', submenu: 'theme' },
  },
  {
    id: 'light-mode', label: '/light-mode', hint: 'Switch the site to light mode',
    action: { kind: 'send', text: 'Switch the site to light mode.' },
  },
  {
    id: 'dark-mode', label: '/dark-mode', hint: 'Switch the site to dark mode',
    action: { kind: 'send', text: 'Switch the site to dark mode.' },
  },
]

const WIZARD_STYLES = ['You decide', 'Photorealistic', 'Illustration', '3D render', 'Minimalist', 'Cinematic', 'Watercolor']
const WIZARD_MOODS = ['You decide', 'Bright & airy', 'Warm', 'Moody', 'Golden hour', 'Studio']
const WIZARD_ASPECTS: [string, string][] = [
  ['', 'Auto'], ['16:9', '16:9'], ['1:1', '1:1'], ['9:16', '9:16'], ['4:3', '4:3'], ['3:2', '3:2'],
]
const WIZARD_QUALITIES: [string, string][] = [
  ['1K', '1K'], ['2K', '2K (recommended)'], ['4K', '4K — ~1.5x cost'],
]

/** Chips PLUS a free-text input sharing one value: picking a chip fills the
 *  input, typing anything (including clearing it back to empty) overrides —
 *  there's no separate "custom" mode to switch into. Empty/"You decide" both
 *  mean the same thing to the server (`image_prompting.build_image_prompt`'s
 *  default clause), so this never needs to special-case which one is active. */
function WizardChipsWithInput({
  options, value, onChange, placeholder,
}: {
  options: string[]
  value: string
  onChange: (v: string) => void
  placeholder: string
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap gap-1">
        {options.map((o) => (
          <button
            key={o}
            type="button"
            onClick={() => onChange(o === 'You decide' ? '' : o)}
            className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${
              value === o || (o === 'You decide' && !value)
                ? 'border-emerald-500 bg-emerald-500/15 text-emerald-300'
                : 'border-zinc-700 text-zinc-400 hover:bg-zinc-800'
            }`}
          >
            {o}
          </button>
        ))}
      </div>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-2.5 py-1.5 text-[11px] text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500"
      />
    </div>
  )
}

/** Guided `/generate-image` — a few quick questions (each with a "You decide"
 *  escape hatch AND a free-text override) so a vague ask doesn't produce a
 *  vague image, without forcing a pick from a fixed list. Generates DIRECTLY
 *  (`merlin.generateImage`) rather than composing an English sentence and
 *  sending it through the agent — the whole point is the user already told
 *  us style/mood/aspect/quality structurally; re-parsing that out of prose
 *  server-side would be strictly lossier. Selected-section context seeds the
 *  description placeholder when available. */
function ImageGenWizard({ selectedLabel, onGenerate, onCancel }: {
  selectedLabel: string | null
  onGenerate: (opts: { prompt: string; style?: string; mood?: string; aspect?: string; size?: string }) => void
  onCancel: () => void
}) {
  const [desc, setDesc] = useState('')
  const [style, setStyle] = useState('')
  const [mood, setMood] = useState('')
  const [aspect, setAspect] = useState('')
  const [quality, setQuality] = useState('2K')

  const generate = () => {
    const prompt = desc.trim() || (selectedLabel ? `something that fits the ${selectedLabel} section` : 'an image for this page')
    onGenerate({ prompt, style: style.trim() || undefined, mood: mood.trim() || undefined, aspect: aspect || undefined, size: quality })
  }

  return (
    <div className="mb-2 space-y-2 rounded-lg border border-zinc-700 bg-zinc-950/60 p-2.5">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-emerald-400">
          <Image className="h-3 w-3" /> Generate an image
        </span>
        <button type="button" onClick={onCancel} className="text-zinc-500 hover:text-zinc-300">
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      <textarea
        value={desc}
        onChange={(e) => setDesc(e.target.value)}
        rows={2}
        placeholder={selectedLabel ? `Describe it — e.g. "a photo for the ${selectedLabel} background"` : 'Describe what to depict…'}
        className="w-full resize-none rounded-lg border border-zinc-700 bg-zinc-950 px-2.5 py-1.5 text-xs text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500"
      />
      <div>
        <p className="mb-1 text-[10px] font-medium text-zinc-500">Style</p>
        <WizardChipsWithInput options={WIZARD_STYLES} value={style} onChange={setStyle} placeholder="Or describe a style…" />
      </div>
      <div>
        <p className="mb-1 text-[10px] font-medium text-zinc-500">Mood & light</p>
        <WizardChipsWithInput options={WIZARD_MOODS} value={mood} onChange={setMood} placeholder="Or describe a mood/lighting…" />
      </div>
      <div className="flex items-center gap-2">
        <select value={aspect} onChange={(e) => setAspect(e.target.value)} className="rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1 text-[11px] text-zinc-200">
          {WIZARD_ASPECTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <select value={quality} onChange={(e) => setQuality(e.target.value)} className="rounded-lg border border-zinc-700 bg-zinc-950 px-2 py-1 text-[11px] text-zinc-200" title="Output resolution">
          {WIZARD_QUALITIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <button
          type="button"
          onClick={generate}
          className="ml-auto flex items-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-1.5 text-xs font-semibold text-zinc-950 hover:bg-emerald-400"
        >
          <Sparkles className="h-3.5 w-3.5" /> Generate
        </button>
      </div>
    </div>
  )
}

const EXAMPLE_PROMPTS = [
  'Make this page feel more premium',
  'Add a testimonials section',
  'Switch to light mode',
  'Generate a hero image',
]

/** The dropdown itself — top-level commands or whichever submenu is open.
 *  Positioned above the composer (an upward-opening menu, like a real chat
 *  slash-command palette) so it never covers the textarea it's driven from. */
function SlashMenu({ items, activeIndex, onHover, onPick }: {
  items: MenuItem[]
  activeIndex: number
  onHover: (i: number) => void
  onPick: (item: MenuItem) => void
}) {
  if (items.length === 0) {
    return (
      <div className="absolute bottom-full left-0 right-0 z-20 mb-1 rounded-lg border border-zinc-700 bg-zinc-900 p-2 text-[11px] text-zinc-500 shadow-xl">
        No matches.
      </div>
    )
  }
  return (
    <div className="absolute bottom-full left-0 right-0 z-20 mb-1 max-h-56 overflow-y-auto rounded-lg border border-zinc-700 bg-zinc-900 p-1 shadow-xl">
      {items.map((item, i) => (
        <button
          key={item.key}
          onMouseEnter={() => onHover(i)}
          onClick={() => onPick(item)}
          className={`flex w-full flex-col items-start gap-0 rounded px-2 py-1.5 text-left ${
            i === activeIndex ? 'bg-zinc-800' : ''
          }`}
        >
          <span className="font-mono text-xs text-emerald-300">{item.title}</span>
          {item.sub && <span className="text-[11px] text-zinc-500">{item.sub}</span>}
        </button>
      ))}
    </div>
  )
}

export function MerlinDrawer({ merlin, selectedLabel }: { merlin: ReturnType<typeof useMerlin>; selectedLabel: string | null }) {
  const premium = usePremium()
  const {
    open, setOpen, messages, send, sending, error, tier, setTier, width, setWidth, setWidthLive,
    expanded, setExpanded,
    newConversation, status, liveSteps, schema,
    attachments, addAttachment, addAttachmentFromUrl, removeAttachment, attachmentUploading, attachmentError,
  } = merlin
  const [input, setInput] = useState('')
  const [activeTab, setActiveTab] = useState<'chat' | 'assets' | 'chats'>('chat')
  const listRef = useRef<HTMLDivElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Slash commands. `slashQuery` is only non-null for a bare "/word" with no
  // space yet — once the user keeps typing past a command (a real sentence
  // that happens to start with '/') the menu gets out of the way.
  const [submenu, setSubmenu] = useState<'add-section' | 'theme' | null>(null)
  const [activeIndex, setActiveIndex] = useState(0)
  const [wizardOpen, setWizardOpen] = useState(false)
  const slashQuery = !submenu && /^\/[a-z-]*$/i.test(input) ? input.slice(1).toLowerCase() : null

  const commandItems: MenuItem[] = useMemo(
    () => SLASH_COMMANDS
      .filter((c) => slashQuery !== null && c.id.includes(slashQuery))
      .map((c) => ({ key: c.id, title: c.label, sub: c.hint, onPick: () => runCommand(c) })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [slashQuery],
  )
  const submenuItems: MenuItem[] = useMemo(() => {
    if (submenu === 'add-section') {
      const presets = (schema?.sectionPresets ?? []).map((p) => ({
        key: `preset:${p.name}`, title: p.label, sub: p.blurb,
        text: `Add a ${p.label} section${p.blurb ? ` — ${p.blurb}.` : '.'}`,
      }))
      const plain = Object.entries(schema?.blocks ?? {}).map(([type, b]) => ({
        key: `block:${type}`, title: b.label, sub: undefined as string | undefined,
        text: `Add a ${b.label} section.`,
      }))
      return [...presets, ...plain].map((it) => ({
        key: it.key, title: it.title, sub: it.sub, onPick: () => pickText(it.text),
      }))
    }
    if (submenu === 'theme') {
      return (schema?.themePresets ?? []).map((p) => ({
        key: `theme:${p.id}`, title: p.name, sub: p.blurb,
        onPick: () => pickText(`Switch the theme to ${p.name}.`),
      }))
    }
    return []
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [submenu, schema])

  const activeItems = submenu ? submenuItems : commandItems
  const menuOpen = submenu !== null || (slashQuery !== null && commandItems.length > 0)

  useEffect(() => { setActiveIndex(0) }, [slashQuery, submenu])

  function focusTextarea(cursorAt?: number) {
    requestAnimationFrame(() => {
      const el = textareaRef.current
      if (!el) return
      el.focus()
      if (cursorAt !== undefined) el.setSelectionRange(cursorAt, cursorAt)
    })
  }

  /** A submenu pick lands as editable text — the user still reviews/adjusts
   *  before sending, same as a plain typed message. */
  function pickText(text: string) {
    setInput(text)
    setSubmenu(null)
    focusTextarea(text.length)
  }

  function runCommand(cmd: SlashCommand) {
    if (cmd.action.kind === 'submenu') {
      setSubmenu(cmd.action.submenu)
      setInput('')
      return
    }
    if (cmd.action.kind === 'wizard') {
      setWizardOpen(true)
      setInput('')
      return
    }
    if (cmd.action.kind === 'prefill') {
      pickText(cmd.action.text)
      return
    }
    setInput('')
    void send(cmd.action.text)
  }

  // A locked tier could still be sitting in localStorage from a lapsed plan —
  // show it selected but send lite, matching what the server would clamp to.
  const tierLocked = (t: MerlinTierChoice) => !premium && MERLIN_TIERS.find((x) => x.id === t)?.premium === true

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      if (wizardOpen) { setWizardOpen(false); return }
      setOpen(() => false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, setOpen, wizardOpen])

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, sending])

  // Drag the left edge to resize. Listeners live on the window (not the
  // handle) so the drag survives the pointer outrunning the 4px strip.
  //
  // rAF-throttled: a high-poll mouse fires well over 60 mousemove events/sec,
  // and each one was driving a full re-render (the message list, every
  // StepTrail screenshot thumbnail, and — because index.tsx derives
  // reservedRight from this width — the canvas bridge re-running against the
  // preview iframe) PLUS a synchronous localStorage write. Coalescing to one
  // update per frame during the drag, and persisting only once on release,
  // removes both costs without changing the interaction.
  const startResize = (e: React.MouseEvent) => {
    e.preventDefault()
    let rafId = 0
    let latestX = e.clientX
    const applyLive = () => {
      rafId = 0
      setWidthLive(window.innerWidth - latestX)
    }
    const onMove = (ev: MouseEvent) => {
      latestX = ev.clientX
      if (!rafId) rafId = requestAnimationFrame(applyLive)
    }
    const onUp = (ev: MouseEvent) => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      document.body.style.userSelect = ''
      if (rafId) cancelAnimationFrame(rafId)
      setWidth(window.innerWidth - ev.clientX)
    }
    document.body.style.userSelect = 'none'
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  if (!open) return null

  const submit = () => {
    if (sending || !input.trim()) return
    send(input)
    setInput('')
    setSubmenu(null)
  }

  return (
    <div
      className="relative flex shrink-0 flex-col overflow-hidden border-l border-zinc-800 bg-zinc-900"
      style={{ width }}
    >
      {/* Resize handle only makes sense docked — expanded width tracks the
          viewport (see useMerlin's expandedWidth), not a dragged pixel value. */}
      {!expanded && (
        <div
          onMouseDown={startResize}
          title={`Drag to resize (${MERLIN_MIN_WIDTH}–${MERLIN_MAX_WIDTH}px)`}
          className="absolute inset-y-0 left-0 z-10 w-1 cursor-col-resize hover:bg-emerald-500/40"
        />
      )}
      <div className="flex items-center justify-between border-b border-zinc-800 px-2 pt-2">
        <div className="flex items-center gap-0.5">
          {([
            { id: 'chat' as const, label: 'Merlin', icon: Sparkles },
            { id: 'assets' as const, label: 'Assets', icon: Image },
            { id: 'chats' as const, label: 'Chats', icon: History },
          ]).map((t) => {
            const Icon = t.icon
            return (
              <button
                key={t.id}
                onClick={() => setActiveTab(t.id)}
                className={`flex items-center gap-1.5 rounded-t-lg border-b-2 px-2.5 py-1.5 text-xs font-medium ${
                  activeTab === t.id ? 'border-emerald-500 text-emerald-400' : 'border-transparent text-zinc-500 hover:text-zinc-300'
                }`}
              >
                <Icon className="h-3.5 w-3.5" /> {t.label}
              </button>
            )
          })}
        </div>
        <div className="flex items-center gap-1 pb-1.5">
          {activeTab === 'chat' && messages.length > 0 && (
            <button onClick={newConversation} className="rounded p-0.5 text-zinc-500 hover:text-zinc-200" title="New conversation">
              <Plus className="h-4 w-4" />
            </button>
          )}
          <button
            onClick={() => setExpanded(!expanded)}
            className="rounded p-0.5 text-zinc-500 hover:text-zinc-200"
            title={expanded ? 'Dock' : 'Pop out — edit in a wider workspace'}
          >
            {expanded ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
          </button>
          <button onClick={() => setOpen(() => false)} className="rounded p-0.5 text-zinc-500 hover:text-zinc-200" title="Close (Esc)"><X className="h-4 w-4" /></button>
        </div>
      </div>

      {activeTab === 'assets' && (
        <AssetLibrary
          variant="panel"
          onPick={(url) => { addAttachmentFromUrl(url); setActiveTab('chat') }}
          onClose={() => setActiveTab('chat')}
        />
      )}
      {activeTab === 'chats' && <ChatsTab merlin={merlin} onOpen={() => setActiveTab('chat')} />}
      {activeTab === 'chat' && <>
          <div ref={listRef} className="flex-1 space-y-3 overflow-y-auto p-3">
            {messages.length === 0 && (
              <div className="space-y-3">
                <p className="text-xs text-zinc-500">
                  Edits apply live to the preview; nothing saves until you hit Save. ⌘Z undoes a turn's
                  edits (an AI-generated image applies as its own step, right after).
                </p>
                <div className="space-y-1">
                  <p className="text-[10px] font-medium uppercase tracking-wider text-zinc-600">Try asking</p>
                  <div className="flex flex-wrap gap-1.5">
                    {EXAMPLE_PROMPTS.map((p) => (
                      <button
                        key={p}
                        onClick={() => { setInput(p); focusTextarea(p.length) }}
                        className="rounded-full border border-zinc-700 px-2.5 py-1 text-[11px] text-zinc-300 hover:border-emerald-600 hover:text-emerald-300"
                      >
                        {p}
                      </button>
                    ))}
                  </div>
                </div>
                <p className="flex items-center gap-1.5 text-[11px] text-zinc-600">
                  <MousePointerClick className="h-3 w-3 shrink-0" /> Select a section in the preview to edit it directly.
                </p>
                <p className="flex items-center gap-1.5 text-[11px] text-zinc-600">
                  <Slash className="h-3 w-3 shrink-0" /> Type <code className="rounded bg-black/30 px-1 py-0.5 font-mono">/</code> for commands — add a section, generate an image, and more.
                </p>
              </div>
            )}
            {messages.map((m, i) => (
              <div key={m.id ?? i} className={m.role === 'user' ? 'ml-6' : 'mr-2'}>
                {m.steps && <StepTrail steps={m.steps} merlin={merlin} premium={premium} />}
                {m.attachments && m.attachments.length > 0 && (
                  <div className="mb-1 flex flex-wrap justify-end gap-1">
                    {m.attachments.map((a, j) => (
                      <img key={j} src={a.url} alt="Attached" className="h-12 w-12 rounded border border-zinc-700 object-cover" />
                    ))}
                  </div>
                )}
                <div className={`rounded-lg px-3 py-2 text-sm ${m.role === 'user' ? 'bg-emerald-500/10 text-emerald-100' : 'bg-zinc-800 text-zinc-100'}`}>
                  {m.role === 'assistant' ? <Markdown>{m.content}</Markdown> : m.content}
                </div>
                {/* Ground truth beats the model's prose: it has claimed
                    effects it never produced, so say plainly when a turn
                    changed nothing. */}
                {m.noChanges && (
                  <p className="mt-1 text-[11px] font-medium text-amber-300/90">No changes applied.</p>
                )}
                {m.role === 'assistant' && m.tier && (
                  <p className="mt-0.5 text-[10px] text-zinc-600">
                    {m.routed ? 'Auto → ' : ''}
                    {MERLIN_TIERS.find((t) => t.id === m.tier)?.label ?? m.tier}
                  </p>
                )}
                {m.results && m.results.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {m.results.map((r, j) => (
                      <span
                        key={j}
                        className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] ${
                          r.ok ? 'border-emerald-700/40 bg-emerald-500/[0.08] text-emerald-300' : 'border-amber-700/40 bg-amber-500/[0.08] text-amber-300'
                        }`}
                      >
                        {r.ok ? <Check className="h-2.5 w-2.5" /> : <AlertCircle className="h-2.5 w-2.5" />}
                        {r.summary}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {sending && (
              <div className="mr-2">
                {/* On an agent turn the trace IS the progress indicator —
                    "Thinking…" for 90s with nothing else says less than
                    "Applied 4 changes / Rendered desktop preview". */}
                <StepTrail steps={liveSteps} live />
                <div className="flex items-center gap-2 rounded-lg bg-zinc-800 px-3 py-2 text-sm text-zinc-400">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" /> {status ?? 'Thinking…'}
                </div>
              </div>
            )}
            {error && <p className="text-xs text-red-400">{error}</p>}
          </div>

          <div className="border-t border-zinc-800 p-3">
            {/* Acknowledges the editor's current selection — "this is what
                your next message will act on" — so a request like "make this
                warmer" has an obvious referent instead of the user wondering
                whether Merlin knows what "this" is. */}
            {selectedLabel && (
              <div
                key={selectedLabel}
                className="mb-2 flex items-center gap-1.5 rounded-lg border border-emerald-700/30 bg-emerald-500/[0.06] px-2.5 py-1.5 text-[11px] text-emerald-300"
              >
                <MousePointerClick className="h-3 w-3 shrink-0" />
                <span>
                  Working on <strong className="font-semibold">{selectedLabel}</strong> — what should we do here?
                </span>
              </div>
            )}
            {/* Model tier. Lite is free on every plan; the rest need Pro/Business.
                Locked options stay visible (and selectable) — the server clamps
                to lite — so the upgrade path is discoverable instead of hidden. */}
            <div className="mb-2 flex rounded-lg border border-zinc-700 p-0.5">
              {MERLIN_TIERS.map((t) => {
                const locked = tierLocked(t.id)
                return (
                  <button
                    key={t.id}
                    onClick={() => setTier(t.id)}
                    title={locked ? `${t.hint} — Pro/Business only` : t.hint}
                    className={`flex flex-1 items-center justify-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium ${
                      tier === t.id ? 'bg-emerald-500 text-zinc-950' : 'text-zinc-400 hover:text-zinc-200'
                    }`}
                  >
                    {locked && <Lock className="h-2.5 w-2.5" />} {t.label}
                  </button>
                )
              })}
            </div>
            {tierLocked(tier) && (
              <p className="mb-2 text-[11px] text-amber-300/90">
                {MERLIN_TIERS.find((t) => t.id === tier)?.label} needs Pro or Business — running on Lite.
              </p>
            )}
            {attachments.length > 0 && (
              <div className="mb-2 flex flex-wrap gap-1.5">
                {attachments.map((a, i) => (
                  <div key={i} className="group relative">
                    <img src={a.url} alt="Attached" className="h-12 w-12 rounded border border-zinc-700 object-cover" />
                    <button
                      onClick={() => removeAttachment(i)}
                      className="absolute -right-1 -top-1 rounded-full bg-zinc-900 p-0.5 text-zinc-400 opacity-0 group-hover:opacity-100 hover:text-red-400"
                      title="Remove"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}
            {attachmentError && <p className="mb-1 text-[11px] text-red-400">{attachmentError}</p>}
            {wizardOpen && (
              <ImageGenWizard
                selectedLabel={selectedLabel}
                onCancel={() => setWizardOpen(false)}
                onGenerate={(opts) => { setWizardOpen(false); void merlin.generateImage(opts) }}
              />
            )}
            <div className={`relative flex gap-2 ${wizardOpen ? 'hidden' : ''}`}>
              {menuOpen && (
                <SlashMenu
                  items={activeItems}
                  activeIndex={activeIndex}
                  onHover={setActiveIndex}
                  onPick={(item) => item.onPick()}
                />
              )}
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (menuOpen) {
                    if (e.key === 'ArrowDown') { e.preventDefault(); setActiveIndex((i) => Math.min(i + 1, activeItems.length - 1)); return }
                    if (e.key === 'ArrowUp') { e.preventDefault(); setActiveIndex((i) => Math.max(i - 1, 0)); return }
                    if (e.key === 'Escape') {
                      // preventDefault alone doesn't stop this reaching the
                      // panel's own window-level Escape-closes-the-drawer
                      // listener (below) — without stopPropagation, dismissing
                      // the command menu closed the whole panel with it.
                      e.preventDefault()
                      e.stopPropagation()
                      setSubmenu(null)
                      setInput('')
                      return
                    }
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      activeItems[activeIndex]?.onPick()
                      return
                    }
                    if (e.key === 'Backspace' && submenu && input === '') { setSubmenu(null); return }
                    return
                  }
                  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() }
                }}
                placeholder={
                  submenu === 'add-section' ? 'Pick a section below, or keep typing…'
                    : submenu === 'theme' ? 'Pick a theme below, or keep typing…'
                    : selectedLabel ? `Change this ${selectedLabel} section…`
                    : 'Describe a change, or type / for commands…'
                }
                rows={2}
                className="w-full resize-none rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
              />
            </div>
            <div className="relative mt-2 flex gap-2">
              <input
                ref={fileRef}
                type="file"
                accept="image/jpeg,image/png,image/gif,image/webp"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file) void addAttachment(file)
                  e.target.value = ''
                }}
              />
              <button
                onClick={() => fileRef.current?.click()}
                disabled={attachmentUploading || attachments.length >= 4}
                title="Attach a photo — place it, use it as a style reference, or generate variations of it"
                className="flex items-center justify-center rounded-lg border border-zinc-700 px-3 py-1.5 text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
              >
                {attachmentUploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Paperclip className="h-4 w-4" />}
              </button>
              <button
                onClick={() => setActiveTab('assets')}
                disabled={attachments.length >= 4}
                title="Attach a past generation or upload from your library"
                className="flex items-center justify-center rounded-lg border border-zinc-700 px-3 py-1.5 text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
              >
                <FolderOpen className="h-4 w-4" />
              </button>
              <button
                onClick={submit}
                disabled={sending || !input.trim()}
                className="flex-1 rounded-lg bg-emerald-500 px-3 py-1.5 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-50"
              >
                {sending ? 'Sending…' : 'Send'}
              </button>
            </div>
          </div>
      </>}
    </div>
  )
}
