import { useState, useMemo, useRef, useCallback, lazy, Suspense } from 'react'
import { Loader2, Sparkles, Type, PenTool, X } from 'lucide-react'
import { editDiagramAI, editDiagramText, saveDiagramSVG } from '../../api/matchaWork'
import type { MWProject } from '../../types/matcha-work'

const Excalidraw = lazy(() =>
  import('@excalidraw/excalidraw').then((m) => ({ default: m.Excalidraw }))
)

type DiagramData = { svg_source: string; storage_url: string; created_from: string }

type Props = {
  projectId: string
  sectionId: string
  diagramData: DiagramData[]
  imageUrl: string
  onClose: () => void
  onUpdated: (project: MWProject) => void
}

type Tab = 'ai' | 'text' | 'visual'

export default function DiagramEditor({ projectId, sectionId, diagramData, imageUrl, onClose, onUpdated }: Props) {
  const [tab, setTab] = useState<Tab>('ai')
  const [instruction, setInstruction] = useState('')
  const [aiLoading, setAiLoading] = useState(false)
  const [aiError, setAiError] = useState<string | null>(null)

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

  // AI Edit
  async function handleAIEdit() {
    if (!instruction.trim() || aiLoading) return
    setAiLoading(true)
    setAiError(null)
    try {
      const result = await editDiagramAI(projectId, sectionId, instruction.trim())
      onUpdated(result)
      setInstruction('')
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
              <div className="flex justify-center bg-zinc-900 rounded-lg p-4">
                <img src={imageUrl} alt="Current diagram" className="max-h-64 object-contain" />
              </div>
              <div>
                <label className="block text-xs text-zinc-400 mb-1.5">Describe your change</label>
                <textarea
                  value={instruction}
                  onChange={(e) => setInstruction(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleAIEdit() } }}
                  placeholder="e.g., Make the title larger, change the red box to blue, add a new node labeled 'Review'..."
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
                {aiLoading ? 'Editing...' : 'Apply with AI'}
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
                        <span className="text-zinc-600">→</span>
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
