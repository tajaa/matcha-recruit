import { useState } from 'react'
import { Loader2, Save, Check } from 'lucide-react'
import { Button } from '../../components/ui'

// Save action for a Deal Flow editor tab. Wraps the tab's async save handler and
// shows transient success / error feedback inline next to the button.
export default function SaveTemplateButton({
  onSave,
  label = 'Save template',
}: {
  onSave: () => Promise<void>
  label?: string
}) {
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState<'idle' | 'saved' | 'error'>('idle')
  const [msg, setMsg] = useState('')

  async function click() {
    setSaving(true)
    setStatus('idle')
    try {
      await onSave()
      setStatus('saved')
      setTimeout(() => setStatus((s) => (s === 'saved' ? 'idle' : s)), 2500)
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Save failed')
      setStatus('error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex items-center gap-2">
      <Button variant="secondary" onClick={click} disabled={saving}>
        {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
        {label}
      </Button>
      {status === 'saved' && (
        <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-400">
          <Check className="h-3.5 w-3.5" /> Saved
        </span>
      )}
      {status === 'error' && <span className="text-xs text-red-400">{msg}</span>}
    </div>
  )
}
