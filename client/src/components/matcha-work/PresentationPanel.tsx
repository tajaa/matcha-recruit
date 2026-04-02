import { useState, useEffect, useCallback, useRef } from 'react'
import {
  ChevronLeft,
  ChevronRight,
  Download,
  Loader2,
  StickyNote,
  Pencil,
  Send,
  X,
} from 'lucide-react'
import type { PresentationSlide, PresentationState } from '../../types/matcha-work'
import { getPresentationPdf } from '../../api/matchaWork'

const THEMES: Record<string, { bg: string; accent: string; text: string; slideBg: string }> = {
  professional: { bg: '#1a1a2e', accent: '#4ade80', text: '#f1f5f9', slideBg: '#16213e' },
  minimal:      { bg: '#ffffff', accent: '#334155', text: '#0f172a', slideBg: '#f8fafc' },
  bold:         { bg: '#0f172a', accent: '#f59e0b', text: '#f8fafc', slideBg: '#1e293b' },
}

interface PresentationPanelProps {
  state: Record<string, unknown>
  threadId: string
  onEditSlide: (slideIndex: number, instruction: string) => void
  lightMode: boolean
  streaming: boolean
}

/** Normalize both standalone and workbook-nested presentation state */
function extractPresentation(state: Record<string, unknown>): PresentationState | null {
  // Standalone: top-level keys
  if (state.slides || state.presentation_title) {
    return {
      presentation_title: (state.presentation_title as string) ?? null,
      subtitle: (state.subtitle as string) ?? null,
      theme: (state.theme as string) ?? null,
      slides: (state.slides as PresentationSlide[]) ?? null,
      cover_image_url: (state.cover_image_url as string) ?? null,
      generated_at: (state.generated_at as string) ?? null,
    }
  }
  // Workbook-nested
  const nested = state.presentation as Record<string, unknown> | undefined
  if (nested && typeof nested === 'object') {
    return {
      presentation_title: (nested.title as string) ?? (nested.presentation_title as string) ?? null,
      subtitle: (nested.subtitle as string) ?? null,
      theme: (nested.theme as string) ?? null,
      slides: (nested.slides as PresentationSlide[]) ?? null,
      cover_image_url: (nested.cover_image_url as string) ?? null,
      generated_at: (nested.generated_at as string) ?? null,
    }
  }
  return null
}

export default function PresentationPanel({
  state,
  threadId,
  onEditSlide,
  lightMode,
  streaming,
}: PresentationPanelProps) {
  const pres = extractPresentation(state)
  const rawSlides = pres?.slides ?? []
  const hasCover = !!pres?.cover_image_url || !!pres?.presentation_title
  // Total count includes virtual cover slide at position 0
  const totalSlides = hasCover ? rawSlides.length + 1 : rawSlides.length
  const theme = THEMES[pres?.theme ?? 'professional'] ?? THEMES.professional

  const [currentIndex, setCurrentIndex] = useState(0)
  const [showNotes, setShowNotes] = useState(false)
  const [editing, setEditing] = useState(false)
  const [editInput, setEditInput] = useState('')
  const [downloadingPdf, setDownloadingPdf] = useState(false)
  const editRef = useRef<HTMLInputElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  // Clamp index when slides change
  useEffect(() => {
    if (currentIndex >= totalSlides && totalSlides > 0) {
      setCurrentIndex(totalSlides - 1)
    }
  }, [totalSlides, currentIndex])

  // Focus edit input
  useEffect(() => {
    if (editing) editRef.current?.focus()
  }, [editing])

  // Keyboard navigation
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (editing) return
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
        e.preventDefault()
        setCurrentIndex((i) => Math.min(i + 1, totalSlides - 1))
      } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
        e.preventDefault()
        setCurrentIndex((i) => Math.max(i - 1, 0))
      }
    },
    [totalSlides, editing]
  )

  useEffect(() => {
    const el = panelRef.current
    if (!el) return
    el.addEventListener('keydown', handleKeyDown)
    return () => el.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  async function handleDownloadPdf() {
    setDownloadingPdf(true)
    try {
      const { pdf_url } = await getPresentationPdf(threadId)
      window.open(pdf_url, '_blank')
    } catch {
      // silent — user can retry
    }
    setDownloadingPdf(false)
  }

  function handleEditSubmit() {
    const instruction = editInput.trim()
    if (!instruction || backendSlideIndex < 0) return
    onEditSlide(backendSlideIndex, instruction)
    setEditInput('')
    setEditing(false)
  }

  if (!pres || totalSlides === 0) {
    return (
      <div
        className="flex w-full items-center justify-center"
        style={{ background: lightMode ? '#f8fafc' : '#18181b' }}
      >
        <p className={lightMode ? 'text-zinc-400 text-sm' : 'text-zinc-500 text-sm'}>
          No slides yet — ask the AI to create a presentation.
        </p>
      </div>
    )
  }

  const isCover = hasCover && currentIndex === 0
  // Map display index → actual slide in the array (cover is virtual, not in rawSlides)
  const slide = isCover ? null : rawSlides[hasCover ? currentIndex - 1 : currentIndex]
  // Slide index for backend edit (offset by cover)
  const backendSlideIndex = hasCover ? currentIndex - 1 : currentIndex

  // Toolbar colors
  const tb = lightMode
    ? { bg: 'bg-zinc-100 border-zinc-200', text: 'text-zinc-600', btn: 'text-zinc-500 hover:text-zinc-900', disabled: 'text-zinc-300' }
    : { bg: 'bg-zinc-900 border-zinc-800', text: 'text-zinc-300', btn: 'text-zinc-400 hover:text-white', disabled: 'text-zinc-600' }

  return (
    <div
      ref={panelRef}
      tabIndex={0}
      className="flex w-full flex-col outline-none"
      style={{ background: lightMode ? '#f8fafc' : '#18181b' }}
    >
      {/* Toolbar */}
      <div className={`flex items-center justify-between px-4 py-2 border-b ${tb.bg}`}>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setCurrentIndex((i) => Math.max(i - 1, 0))}
            disabled={currentIndex === 0}
            className={`p-1 rounded transition-colors ${currentIndex === 0 ? tb.disabled : tb.btn}`}
          >
            <ChevronLeft size={16} />
          </button>
          <span className={`text-xs font-medium ${tb.text} tabular-nums`}>
            {currentIndex + 1} / {totalSlides}
          </span>
          <button
            onClick={() => setCurrentIndex((i) => Math.min(i + 1, totalSlides - 1))}
            disabled={currentIndex === totalSlides - 1}
            className={`p-1 rounded transition-colors ${currentIndex === totalSlides - 1 ? tb.disabled : tb.btn}`}
          >
            <ChevronRight size={16} />
          </button>
        </div>

        <div className="flex items-center gap-1.5">
          <button
            onClick={() => setEditing(!editing)}
            disabled={streaming || isCover}
            title={isCover ? 'Cover slide is auto-generated' : 'Edit this slide'}
            className={`p-1.5 rounded transition-colors ${editing ? 'bg-emerald-600 text-white' : tb.btn} disabled:opacity-40`}
          >
            <Pencil size={14} />
          </button>
          <button
            onClick={() => setShowNotes(!showNotes)}
            title="Speaker notes"
            className={`p-1.5 rounded transition-colors ${showNotes ? 'bg-amber-600 text-white' : tb.btn}`}
          >
            <StickyNote size={14} />
          </button>
          <button
            onClick={handleDownloadPdf}
            disabled={downloadingPdf}
            title="Download PDF"
            className={`p-1.5 rounded transition-colors ${tb.btn} disabled:opacity-40`}
          >
            {downloadingPdf ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
          </button>
        </div>
      </div>

      {/* Main slide area */}
      <div className="flex-1 flex items-center justify-center p-6 overflow-hidden">
        <div
          className="w-full relative rounded-lg shadow-2xl overflow-hidden"
          style={{
            aspectRatio: '16 / 9',
            maxHeight: '100%',
            background: isCover ? theme.bg : theme.slideBg,
            borderTop: isCover ? 'none' : `4px solid ${theme.accent}`,
            borderLeft: isCover ? `6px solid ${theme.accent}` : 'none',
          }}
        >
          {/* Cover image */}
          {isCover && pres.cover_image_url && (
            <img
              src={pres.cover_image_url}
              alt=""
              className="absolute inset-0 w-full h-full object-cover opacity-25"
            />
          )}

          {/* Slide content */}
          <div className="relative z-10 h-full flex flex-col justify-center px-[6%] py-[5%]">
            {isCover ? (
              <>
                <h1
                  className="font-extrabold leading-tight mb-3"
                  style={{ color: theme.text, fontSize: 'clamp(1.25rem, 3.5vw, 2.75rem)', letterSpacing: '-0.5px' }}
                >
                  {pres.presentation_title ?? 'Presentation'}
                </h1>
                {pres.subtitle && (
                  <p
                    className="font-medium"
                    style={{ color: theme.accent, fontSize: 'clamp(0.75rem, 1.5vw, 1.25rem)' }}
                  >
                    {pres.subtitle}
                  </p>
                )}
              </>
            ) : (
              <>
                <h2
                  className="font-bold mb-4"
                  style={{
                    color: theme.accent,
                    fontSize: 'clamp(1rem, 2.5vw, 1.75rem)',
                    letterSpacing: '-0.3px',
                  }}
                >
                  {slide?.title}
                </h2>
                {slide?.bullets && slide.bullets.length > 0 && (
                  <ul className="space-y-2">
                    {slide.bullets.map((b, i) => (
                      <li
                        key={i}
                        className="flex items-start gap-2"
                        style={{ color: theme.text, fontSize: 'clamp(0.65rem, 1.3vw, 1.05rem)', lineHeight: 1.5 }}
                      >
                        <span style={{ color: theme.accent }} className="shrink-0 mt-0.5 text-xs">
                          &#x25B8;
                        </span>
                        <span>{b}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </div>
        </div>
      </div>

      {/* Edit bar — not available on cover slide */}
      {editing && !isCover && (
        <div className={`px-4 py-2 border-t ${lightMode ? 'border-zinc-200 bg-zinc-50' : 'border-zinc-800 bg-zinc-900'}`}>
          <div className="flex items-center gap-2">
            <span className={`text-xs shrink-0 ${lightMode ? 'text-zinc-400' : 'text-zinc-500'}`}>
              Slide {currentIndex + 1}:
            </span>
            <input
              ref={editRef}
              value={editInput}
              onChange={(e) => setEditInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleEditSubmit(); if (e.key === 'Escape') setEditing(false) }}
              placeholder="e.g. Add a bullet about day-one orientation"
              disabled={streaming}
              className={`flex-1 text-sm rounded px-2.5 py-1.5 border focus:outline-none focus:border-emerald-600 disabled:opacity-50 ${
                lightMode
                  ? 'bg-white text-zinc-900 border-zinc-300 placeholder-zinc-400'
                  : 'bg-zinc-800 text-white border-zinc-700 placeholder-zinc-500'
              }`}
            />
            <button
              onClick={handleEditSubmit}
              disabled={!editInput.trim() || streaming}
              className="p-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded transition-colors disabled:opacity-40"
            >
              <Send size={14} />
            </button>
            <button
              onClick={() => { setEditing(false); setEditInput('') }}
              className={`p-1.5 rounded transition-colors ${lightMode ? 'text-zinc-400 hover:text-zinc-700' : 'text-zinc-500 hover:text-white'}`}
            >
              <X size={14} />
            </button>
          </div>
        </div>
      )}

      {/* Speaker notes */}
      {showNotes && !isCover && (
        <div className={`px-4 py-3 border-t ${lightMode ? 'border-zinc-200 bg-zinc-50' : 'border-zinc-800 bg-zinc-900/80'}`}>
          <p className={`text-xs font-medium mb-1 ${lightMode ? 'text-zinc-400' : 'text-zinc-500'}`}>
            Speaker Notes
          </p>
          <p className={`text-sm leading-relaxed ${lightMode ? 'text-zinc-600' : 'text-zinc-300'}`}>
            {slide?.speaker_notes || 'No notes for this slide.'}
          </p>
        </div>
      )}

      {/* Thumbnail strip */}
      {totalSlides > 1 && (
        <div className={`px-4 py-2 border-t overflow-x-auto ${lightMode ? 'border-zinc-200 bg-zinc-100' : 'border-zinc-800 bg-zinc-900'}`}>
          <div className="flex gap-1.5">
            {Array.from({ length: totalSlides }, (_, i) => {
              const active = i === currentIndex
              const isThumbCover = hasCover && i === 0
              const thumbSlide = isThumbCover ? null : rawSlides[hasCover ? i - 1 : i]
              return (
                <button
                  key={i}
                  onClick={() => setCurrentIndex(i)}
                  title={isThumbCover ? (pres?.presentation_title ?? 'Cover') : (thumbSlide?.title ?? `Slide ${i + 1}`)}
                  className={`shrink-0 rounded px-2.5 py-1 text-[10px] font-medium transition-colors ${
                    active
                      ? 'bg-emerald-600 text-white'
                      : lightMode
                        ? 'bg-zinc-200 text-zinc-500 hover:bg-zinc-300 hover:text-zinc-700'
                        : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200'
                  }`}
                >
                  {isThumbCover ? '\u25A0' : i + (hasCover ? 0 : 1)}
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
