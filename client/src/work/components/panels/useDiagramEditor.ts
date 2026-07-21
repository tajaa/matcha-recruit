import { useState, useMemo, useRef, useCallback } from 'react'
import { editDiagramAI, editDiagramText, saveDiagramSVG } from '../../api/matchaWork'
import type { MWProject } from '../../types'

export type DiagramData = { svg_source: string; storage_url: string; created_from: string }
export type Region = { x: number; y: number; width: number; height: number }
export type Tab = 'ai' | 'text' | 'visual'

type Args = {
  projectId: string
  sectionId: string
  diagramData: DiagramData[]
  onUpdated: (project: MWProject) => void
}

function clamp(v: number, min: number, max: number) {
  return Math.max(min, Math.min(max, v))
}

export function useDiagramEditor({ projectId, sectionId, diagramData, onUpdated }: Args) {
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

  return {
    tab,
    setTab,
    instruction,
    setInstruction,
    aiLoading,
    aiError,
    regionMode,
    setRegionMode,
    region,
    setRegion,
    dragging,
    setDragging,
    imgRef,
    containerRef,
    textElements,
    textEdits,
    setTextEdits,
    textLoading,
    excalidrawAPIRef,
    visualLoading,
    pctToContainerStyle,
    handleMouseDown,
    handleMouseMove,
    handleMouseUp,
    previewRect,
    handleAIEdit,
    handleTextEdit,
    handleExcalidrawSave,
  }
}
