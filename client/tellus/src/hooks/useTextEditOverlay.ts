// In-place text editing for the designer.
//
// Konva has no text caret — the standard trick is to hide the Konva.Text node
// and float a real <textarea> over exactly where it sat, styled to match, so
// the user gets native selection/IME/spellcheck. The caller hides the node
// (DesignerCanvas takes `editingLayerId`) and applies the committed string
// through the history hook, so one edit is one undo step.
//
// v1 scope: rotation is ignored while editing (the textarea renders upright).
// Rotated text is rare on a flyer and the transform math to match a rotated,
// scaled box is not worth the first cut.
import { useCallback, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import type Konva from 'konva'
import type { DesignLayer } from '../api/types'

type TextLayer = Extract<DesignLayer, { type: 'text' }>

export interface TextEditState {
  layerId: string
  style: CSSProperties
  value: string
}

export function useTextEditOverlay() {
  const [editing, setEditingState] = useState<TextEditState | null>(null)
  // Mirror of the state. commit() has to read the pending text SYNCHRONOUSLY —
  // a useState updater is deferred to the next render, so reading it there
  // would always hand the caller a stale (null) value.
  const current = useRef<TextEditState | null>(null)
  const setEditing = useCallback((next: TextEditState | null) => {
    current.current = next
    setEditingState(next)
  }, [])

  const begin = useCallback((layer: TextLayer, node: Konva.Text) => {
    const stage = node.getStage()
    if (!stage) return
    // Scale is read off the live stage, not passed in: fit-to-container lives
    // inside DesignerCanvas, so a scale threaded down from the page would sit
    // at its initial guess until some unrelated state change re-rendered it.
    const stageScale = stage.scaleX() || 1
    // Absolute position is relative to the stage's own box, so the overlay is
    // positioned inside the stage's container (position:relative), not the page.
    const pos = node.getAbsolutePosition()
    const style: CSSProperties = {
      position: 'absolute',
      left: `${pos.x}px`,
      top: `${pos.y}px`,
      width: `${layer.width * stageScale}px`,
      // Konva's line height is a multiplier of fontSize; the textarea needs it
      // in the same terms or the wrapped lines drift out of register.
      fontSize: `${layer.fontSize * stageScale}px`,
      lineHeight: layer.lineHeight,
      letterSpacing: `${layer.letterSpacing * stageScale}px`,
      fontFamily: `"${layer.fontFamily}"`,
      fontWeight: layer.fontStyle === 'bold' ? 700 : 400,
      fontStyle: layer.fontStyle === 'italic' ? 'italic' : 'normal',
      textAlign: layer.align,
      color: layer.fill,
      opacity: layer.opacity,
      background: 'transparent',
      border: '1px dashed rgba(249,115,22,0.9)',
      outline: 'none',
      padding: 0,
      margin: 0,
      resize: 'none',
      overflow: 'hidden',
      zIndex: 20,
    }
    setEditing({ layerId: layer.id, style, value: layer.text })
  }, [setEditing])

  const onChange = useCallback((value: string) => {
    if (!current.current) return
    setEditing({ ...current.current, value })
  }, [setEditing])

  // Returns the pending edit so the caller can push it through history as one
  // commit; null when nothing was open.
  const commit = useCallback((): { layerId: string; text: string } | null => {
    const open = current.current
    setEditing(null)
    return open ? { layerId: open.layerId, text: open.value } : null
  }, [setEditing])

  const cancel = useCallback(() => setEditing(null), [setEditing])

  return { editing, begin, onChange, commit, cancel }
}
