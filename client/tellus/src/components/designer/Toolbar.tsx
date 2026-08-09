// Designer top bar: insert actions, history, save state.
import { Circle, Minus, QrCode, Redo2, Save, Square, Type, Undo2 } from 'lucide-react'
import { Button } from '../ui'

export interface ToolbarProps {
  onAddText: () => void
  onAddShape: (shape: 'rect' | 'circle' | 'line') => void
  onAddQr: () => void
  onUndo: () => void
  onRedo: () => void
  canUndo: boolean
  canRedo: boolean
  dirty: boolean
  saving: boolean
  onSave: () => void
  hasQr: boolean
}

export function Toolbar({
  onAddText, onAddShape, onAddQr, onUndo, onRedo, canUndo, canRedo, dirty, saving, onSave, hasQr,
}: ToolbarProps) {
  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-tu-border bg-tu-panel px-3 py-2">
      <Button size="sm" variant="soft" onClick={onAddText}><Type className="h-3.5 w-3.5" /> Text</Button>
      <Button size="sm" variant="soft" onClick={() => onAddShape('rect')}><Square className="h-3.5 w-3.5" /></Button>
      <Button size="sm" variant="soft" onClick={() => onAddShape('circle')}><Circle className="h-3.5 w-3.5" /></Button>
      <Button size="sm" variant="soft" onClick={() => onAddShape('line')}><Minus className="h-3.5 w-3.5" /></Button>
      <Button size="sm" variant="soft" onClick={onAddQr} disabled={hasQr} title={hasQr ? 'The flyer already has a claim QR' : 'Add the claim QR'}>
        <QrCode className="h-3.5 w-3.5" /> Claim QR
      </Button>

      <div className="mx-1 h-5 w-px bg-tu-border" />
      <Button size="sm" variant="ghost" onClick={onUndo} disabled={!canUndo}><Undo2 className="h-3.5 w-3.5" /></Button>
      <Button size="sm" variant="ghost" onClick={onRedo} disabled={!canRedo}><Redo2 className="h-3.5 w-3.5" /></Button>

      <div className="ml-auto flex items-center gap-3">
        <span className="text-xs text-tu-faint">{saving ? 'Saving…' : dirty ? 'Unsaved changes' : 'All changes saved'}</span>
        <Button size="sm" variant="soft" loading={saving} onClick={onSave} disabled={!dirty}>
          <Save className="h-3.5 w-3.5" /> Save
        </Button>
      </div>
    </div>
  )
}
