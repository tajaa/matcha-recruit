import { Loader2, Mail, Sparkles } from 'lucide-react'
import { Button } from '../../ui'

interface CopilotHeaderProps {
  streaming: boolean
  incidentIsClosed: boolean
  closingIncident: boolean
  emergencyAlertActive: boolean
  onRequestInfo: () => void
  onCloseIncident: () => void
}

export function CopilotHeader({
  streaming, incidentIsClosed, closingIncident, emergencyAlertActive, onRequestInfo, onCloseIncident,
}: CopilotHeaderProps) {
  return (
    <div className="shrink-0 border-b border-white/[0.06] px-5 py-3">
      <div className="flex items-center gap-2">
        <Sparkles className="w-4 h-4 text-emerald-400" />
        <h2 className="text-base font-semibold text-zinc-100">Copilot</h2>
        {streaming && (
          <span className="text-xs text-zinc-500 flex items-center gap-1">
            <Loader2 className="w-3 h-3 animate-spin" /> Thinking…
          </span>
        )}
        <div className="ml-auto flex items-center gap-2">
          {!incidentIsClosed && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onRequestInfo}
            >
              <Mail className="w-3.5 h-3.5" />
              <span className="ml-1.5">Request more info</span>
            </Button>
          )}
          {!incidentIsClosed && (
            <Button
              variant="ghost"
              size="sm"
              disabled={closingIncident || streaming || emergencyAlertActive}
              title={emergencyAlertActive ? 'Acknowledge the OSHA reporting alert first.' : undefined}
              onClick={onCloseIncident}
            >
              {closingIncident ? (
                <span className="flex items-center gap-1">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  Closing…
                </span>
              ) : (
                'Close incident'
              )}
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
