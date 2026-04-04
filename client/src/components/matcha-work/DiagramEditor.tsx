import { useState, useMemo, useRef, useCallback, lazy, Suspense } from 'react'
import { Loader2, Sparkles, Type, PenTool, X, Crop } from 'lucide-react'
import { editDiagramAI, editDiagramText, saveDiagramSVG } from '../../api/matchaWork'
import type { MWProject } from '../../types/matcha-work'

const Excalidraw = lazy(() =>
  import('@excalidraw/excalidraw').then((m) => ({ default: m.Excalidraw }))
)

type DiagramData = { svg_source: string; storage_url: string; created_from: string }
type Region = { x: number; y: number; width: number; height: number }

type Props = {
  projectId: string
  sectionId: string
  diagramData: DiagramData[]
  imageUrl: string
  onClose: () => void
  onUpdated: (project: MWProject) => void
}

type Tab = 'ai' | 'text' | 'visual'

function clamp(v: number, min: number, max: number) {
  return Math.max(min, Math.min(max, v))
}

export default function DiagramEditor({ projectId, sectionId, diagramData, imageUrl, onClose, onUpdated }: Props) {
  const [tab, setTab] = useState<Tab>('ai')
  const [instruction, setInstruction] = useState('')
  const [aiLoading, setAiLoading] = useState(false)
  const [aiError, setAiError] = useState<string | null>(null)

  // Region selection state
  const [regionMode, setRegionMode] = useState(false)
  const [region, setRegion] = useState<Region | null>(null)
  const [dragging, setDragging] = useState(false)
  const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(null)
  const [dragCurrent, setDragCurrent] = useState<{ x: number; y: number } | null>(null)
  const imgRef = useRef<HTMLImageElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const svgSource = diagramData[0]?.svg_source ?? ''

  // Extract text elements from SVG for text editing
  const textElements = useMemo(() => {
    if (!svgSource) return []
    const matches = [...svgSource.matchAll(/>([^<]+)</g)]
    const texts = matches
      .map((m) => m[1].trim())
      .filter((t) => t.length > 0 && t.length < 200)
    return [...new Set(texts)]
  }, [svgSource])

  const [textEdits, setTextEdits] = useState<Record<string, string>>({})
  const [textLoading, setTextLoading] = useState(false)

  const excalidrawAPIRef = useRef<any>(null)
  const [visualLoading, setVisualLoading] = useState(false)

  // Compute the actual rendered image rect within the <img> element (handles object-contain offset)
  function getRenderedImageRect() {
    const img = imgRef.current
    const container = containerRef.current
    if (!img || !container || !img.naturalWidth || !img.naturalHeight) return null

    const imgRect = img.getBoundingClientRect()
    const containerRect = container.getBoundingClientRect()
    const elemW = imgRect.width
    const elemH = imgRect.height
    const imgAspect = img.naturalWidth / img.naturalHeight
    const elemAspect = elemW / elemH

    let renderedW: number, renderedH: number, imgOffsetX: number, imgOffsetY: number
    if (imgAspect > elemAspect) {
      renderedW = elemW
      renderedH = elemW / imgAspect
      imgOffsetX = 0
      imgOffsetY = (elemH - renderedH) / 2
    } else {
      renderedH = elemH
      renderedW = elemH * imgAspect
      imgOffsetX = (elemW - renderedW) / 2
      imgOffsetY = 0
    }

    // Offset from the container's top-left to the rendered image content's top-left
    const offsetX = (imgRect.left - containerRect.left) + imgOffsetX
    const offsetY = (imgRect.top - containerRect.top) + imgOffsetY

    return { renderedW, renderedH, offsetX, offsetY }
  }

  // Convert mouse event to percentage coordinates relative to the actual rendered image
  function toImagePercent(clientX: number, clientY: number): { x: number; y: number } | null {
    const container = containerRef.current
    const dims = getRenderedImageRect()
    if (!container || !dims) return null

    const containerRect = container.getBoundingClientRect()
    const mouseX = clientX - containerRect.left
    const mouseY = clientY - containerRect.top

    const pctX = ((mouseX - dims.offsetX) / dims.renderedW) * 100
    const pctY = ((mouseY - dims.offsetY) / dims.renderedH) * 100

    return { x: clamp(pctX, 0, 100), y: clamp(pctY, 0, 100) }
  }

  // Convert percentage coordinates to CSS position within the container
  function pctToContainerStyle(pctX: number, pctY: number, pctW: number, pctH: number) {
    const dims = getRenderedImageRect()
    if (!dims) {
      return { left: `${pctX}%`, top: `${pctY}%`, width: `${pctW}%`, height: `${pctH}%` }
    }

    return {
      left: `${dims.offsetX + (pctX / 100) * dims.renderedW}px`,
      top: `${dims.offsetY + (pctY / 100) * dims.renderedH}px`,
      width: `${(pctW / 100) * dims.renderedW}px`,
      height: `${(pctH / 100) * dims.renderedH}px`,
    }
  }

  function handleMouseDown(e: React.MouseEvent) {
    if (!regionMode) return
    const pt = toImagePercent(e.clientX, e.clientY)
    if (!pt) return
    setDragging(true)
    setDragStart(pt)
    setDragCurrent(pt)
    setRegion(null)
  }

  function handleMouseMove(e: React.MouseEvent) {
    if (!dragging || !dragStart) return
    const pt = toImagePercent(e.clientX, e.clientY)
    if (pt) setDragCurrent(pt)
  }

  function handleMouseUp() {
    if (!dragging || !dragStart || !dragCurrent) {
      setDragging(false)
      return
    }
    setDragging(false)

    const x = Math.min(dragStart.x, dragCurrent.x)
    const y = Math.min(dragStart.y, dragCurrent.y)
    const width = Math.abs(dragCurrent.x - dragStart.x)
    const height = Math.abs(dragCurrent.y - dragStart.y)

    // Ignore tiny selections (accidental clicks)
    if (width < 2 && height < 2) {
      setDragStart(null)
      setDragCurrent(null)
      return
    }

    setRegion({ x, y, width, height })
    setDragStart(null)
    setDragCurrent(null)
  }

  // Compute the preview rectangle (either final region or in-progress drag)
  const previewRect = useMemo(() => {
    if (region) return region
    if (dragging && dragStart && dragCurrent) {
      return {
        x: Math.min(dragStart.x, dragCurrent.x),
        y: Math.min(dragStart.y, dragCurrent.y),
        width: Math.abs(dragCurrent.x - dragStart.x),
        height: Math.abs(dragCurrent.y - dragStart.y),
      }
    }
    return null
  }, [region, dragging, dragStart, dragCurrent])

  // AI Edit
  async function handleAIEdit() {
    if (!instruction.trim() || aiLoading) return
    setAiLoading(true)
    setAiError(null)
    try {
      const result = await editDiagramAI(projectId, sectionId, instruction.trim(), region ?? undefined)
      onUpdated(result)
      setInstruction('')
      setRegion(null)
      setRegionMode(false)
    } catch (e) {
      setAiError(e instanceof Error ? e.message : 'Failed to edit diagram')
    }
    setAiLoading(false)
  }

  // Text Edit
  async function handleTextEdit() {
    const edits = Object.entries(textEdits)
      .filter(([old_text, new_text]) => new_text && new_text !== old_text)
      .map(([old_text, new_text]) => ({ old_text, new_text }))
    if (edits.length === 0) return
    setTextLoading(true)
    try {
      const result = await editDiagramText(projectId, sectionId, edits)
      onUpdated(result)
      setTextEdits({})
    } catch {}
    setTextLoading(false)
  }

  // Excalidraw export
  const handleExcalidrawSave = useCallback(async () => {
    const api = excalidrawAPIRef.current
    if (!api) return
    setVisualLoading(true)
    try {
      const svgEl = await api.exportToSvg()
      const svgStr = new XMLSerializer().serializeToString(svgEl)
      const result = await saveDiagramSVG(projectId, sectionId, svgStr)
      onUpdated(result)
    } catch {}
    setVisualLoading(false)
  }, [projectId, sectionId, onUpdated])

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
      <div className="bg-[#1e1e1e] border border-zinc-700 rounded-xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-zinc-700">
          <h2 className="text-sm font-semibold text-zinc-100">Edit Diagram</h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300 transition-colors">
            <X size={16} />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-zinc-700">
          {([
            ['ai', Sparkles, 'AI Edit'] as const,
            ['text', Type, 'Text Edit'] as const,
            ['visual', PenTool, 'Visual Editor'] as const,
          ]).map(([t, Icon, label]) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`flex items-center gap-1.5 px-5 py-2.5 text-xs font-medium transition-colors ${
                tab === t ? 'text-zinc-100 border-b-2 border-emerald-500' : 'text-zinc-500 hover:text-zinc-300'
              }`}
            >
              <Icon size={12} />
              {label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto">
          {/* AI Edit */}
          {tab === 'ai' && (
            <div className="p-5 space-y-4">
              {/* Diagram preview with region selection overlay */}
              <div
                ref={containerRef}
                className="relative flex justify-center bg-zinc-900 rounded-lg p-4 select-none"
                onMouseDown={handleMouseDown}
                onMouseMove={handleMouseMove}
                onMouseUp={handleMouseUp}
                onMouseLeave={() => { if (dragging) handleMouseUp() }}
                style={{ cursor: regionMode ? 'crosshair' : 'default' }}
              >
                <img
                  ref={imgRef}
                  src={imageUrl}
                  alt="Current diagram"
                  className="max-h-64 object-contain pointer-events-none"
                  draggable={false}
                />

                {/* Selection rectangle */}
                {previewRect && previewRect.width > 0 && previewRect.height > 0 && (
                  <div
                    className="absolute border-2 border-dashed border-emerald-400 bg-emerald-400/10 rounded-sm pointer-events-none"
                    style={pctToContainerStyle(previewRect.x, previewRect.y, previewRect.width, previewRect.height)}
                  />
                )}

                {/* Dim area outside selection when region is set */}
                {region && !dragging && (
                  <div
                    className="absolute pointer-events-none"
                    style={{
                      ...pctToContainerStyle(region.x, region.y, region.width, region.height),
                      boxShadow: '0 0 0 9999px rgba(0,0,0,0.4)',
                    }}
                  />
                )}
              </div>

              {/* Region selection toolbar */}
              <div className="flex items-center gap-2">
                <button
                  onClick={() => {
                    setRegionMode(!regionMode)
                    if (regionMode) { setRegion(null); setDragging(false) }
                  }}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                    regionMode
                      ? 'bg-emerald-700/50 text-emerald-300 border border-emerald-600'
                      : 'bg-zinc-800 text-zinc-400 border border-zinc-700 hover:text-zinc-300'
                  }`}
                >
                  <Crop size={12} />
                  {regionMode ? 'Selecting Region' : 'Select Region'}
                </button>
                {region && (
                  <button
                    onClick={() => setRegion(null)}
                    className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
                  >
                    Clear selection
                  </button>
                )}
                {region && (
                  <span className="text-[10px] text-zinc-600 ml-auto">
                    Region: {region.x.toFixed(0)}%, {region.y.toFixed(0)}% — {region.width.toFixed(0)}x{region.height.toFixed(0)}%
                  </span>
                )}
              </div>

              <div>
                <label className="block text-xs text-zinc-400 mb-1.5">
                  {region ? 'Describe your change (applies only to selected region)' : 'Describe your change'}
                </label>
                <textarea
                  value={instruction}
                  onChange={(e) => setInstruction(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleAIEdit() } }}
                  placeholder={region
                    ? 'e.g., Change this box to blue, replace this text with "Done", remove this arrow...'
                    : 'e.g., Make the title larger, change the red box to blue, add a new node labeled \'Review\'...'
                  }
                  rows={3}
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3.5 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-zinc-500 resize-none"
                />
              </div>
              {aiError && <p className="text-xs text-red-400">{aiError}</p>}
              <button
                onClick={handleAIEdit}
                disabled={!instruction.trim() || aiLoading}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-700 text-sm font-medium text-white hover:bg-emerald-600 disabled:opacity-40 transition-colors"
              >
                {aiLoading ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                {aiLoading ? 'Editing...' : region ? 'Apply to Selection' : 'Apply with AI'}
              </button>
            </div>
          )}

          {/* Text Edit */}
          {tab === 'text' && (
            <div className="p-5 space-y-4">
              {textElements.length === 0 ? (
                <p className="text-sm text-zinc-500">No editable text elements found in this diagram.</p>
              ) : (
                <>
                  <p className="text-xs text-zinc-500">Click any text to edit it directly:</p>
                  <div className="space-y-2 max-h-80 overflow-y-auto">
                    {textElements.map((text) => (
                      <div key={text} className="flex items-center gap-3">
                        <span className="text-xs text-zinc-500 w-40 truncate shrink-0">{text}</span>
                        <span className="text-zinc-600">&rarr;</span>
                        <input
                          value={textEdits[text] ?? text}
                          onChange={(e) => setTextEdits((prev) => ({ ...prev, [text]: e.target.value }))}
                          className="flex-1 rounded border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-xs text-zinc-100 outline-none focus:border-zinc-500"
                        />
                      </div>
                    ))}
                  </div>
                  <button
                    onClick={handleTextEdit}
                    disabled={textLoading || !Object.entries(textEdits).some(([k, v]) => v !== k)}
                    className="flex items-center gap-2 px-4 py-2 rounded-lg bg-zinc-700 text-sm font-medium text-white hover:bg-zinc-600 disabled:opacity-40 transition-colors"
                  >
                    {textLoading ? <Loader2 size={14} className="animate-spin" /> : <Type size={14} />}
                    {textLoading ? 'Applying...' : 'Apply Text Changes'}
                  </button>
                </>
              )}
            </div>
          )}

          {/* Visual Editor (Excalidraw) */}
          {tab === 'visual' && (
            <div className="h-[500px] relative">
              <Suspense fallback={
                <div className="flex items-center justify-center h-full">
                  <Loader2 size={20} className="animate-spin text-zinc-500" />
                </div>
              }>
                <Excalidraw
                  theme="dark"
                  initialData={{
                    appState: { viewBackgroundColor: '#1e1e1e' },
                  }}
                  excalidrawAPI={(api: any) => { excalidrawAPIRef.current = api }}
                />
              </Suspense>
              <div className="absolute bottom-4 right-4 z-20">
                <button
                  onClick={handleExcalidrawSave}
                  disabled={visualLoading}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-700 text-sm font-medium text-white hover:bg-emerald-600 disabled:opacity-40 transition-colors shadow-lg"
                >
                  {visualLoading ? <Loader2 size={14} className="animate-spin" /> : <PenTool size={14} />}
                  Save Diagram
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
