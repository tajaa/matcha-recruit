import { Trash2, FileText, Loader2, Paperclip } from 'lucide-react'
import type { ProjectPanelController } from './useProjectPanel'

export default function AttachmentsPanel({ ctl }: { ctl: ProjectPanelController }) {
  const { files, uploadingFiles, fileInputRef, handleDeleteFile, formatBytes } = ctl
  return (
    <div className="px-4 py-2" style={{ borderBottom: '1px solid #333' }}>
      <div className="flex items-center justify-between mb-1.5">
        <span className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider" style={{ color: '#6a737d' }}>
          <Paperclip size={10} />
          Attachments ({files.length})
        </span>
        <button
          onClick={() => fileInputRef.current?.click()}
          className="text-[10px] px-1.5 py-0.5 rounded transition-colors"
          style={{ color: '#ce9178' }}
        >
          + Add
        </button>
      </div>
      {uploadingFiles.map(name => (
        <div key={name} className="flex items-center gap-2 py-1 text-xs" style={{ color: '#6a737d' }}>
          <Loader2 size={10} className="animate-spin" /> <span className="truncate">{name}</span>
        </div>
      ))}
      {files.map(f => (
        <div key={f.id} className="flex items-center gap-2 py-1 group">
          <FileText size={12} className="shrink-0" style={{ color: '#6a737d' }} />
          <a href={f.storage_url} target="_blank" rel="noopener noreferrer" className="flex-1 text-xs truncate hover:underline" style={{ color: '#d4d4d4' }}>
            {f.filename}
          </a>
          <span className="text-[9px] shrink-0" style={{ color: '#6a737d' }}>{formatBytes(f.file_size)}</span>
          <button
            onClick={() => handleDeleteFile(f.id)}
            className="shrink-0 p-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity"
            style={{ color: '#f87171' }}
          >
            <Trash2 size={10} />
          </button>
        </div>
      ))}
    </div>
  )
}
