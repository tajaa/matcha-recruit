import { Loader2 } from 'lucide-react'
import type { ProjectPanelController } from './useProjectPanel'

export default function PreviewPane({ ctl }: { ctl: ProjectPanelController }) {
  const { loadingPreview, previewUrl } = ctl
  return (
    <div className="flex-1 overflow-hidden" style={{ background: '#252526' }}>
      {loadingPreview ? (
        <div className="flex items-center justify-center h-full">
          <Loader2 size={20} className="animate-spin" style={{ color: '#6a737d' }} />
        </div>
      ) : previewUrl ? (
        <iframe src={previewUrl} className="w-full h-full border-0" title="PDF Preview" />
      ) : (
        <div className="flex items-center justify-center h-full">
          <p className="text-xs" style={{ color: '#6a737d' }}>Could not generate preview</p>
        </div>
      )}
    </div>
  )
}
