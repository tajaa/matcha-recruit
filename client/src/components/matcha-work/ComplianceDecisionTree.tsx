import { useMemo, useCallback, useState } from 'react'
import {
  ReactFlow,
  Background,
  MarkerType,
  type Node,
  type Edge,
  Position,
  Handle,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { ExternalLink } from 'lucide-react'
import type {
  AIReasoningStep,
  ComplianceReasoningCategory,
} from '../../types/matcha-work'
import dagre from '@dagrejs/dagre'

const NODE_W = 300
const NODE_H = 60

const PREC_COLORS: Record<string, { bg: string; text: string }> = {
  floor: { bg: 'bg-emerald-900/60', text: 'text-emerald-300' },
  ceiling: { bg: 'bg-amber-900/60', text: 'text-amber-300' },
  supersede: { bg: 'bg-red-900/60', text: 'text-red-300' },
  additive: { bg: 'bg-blue-900/60', text: 'text-blue-300' },
}

const ARROW = { type: MarkerType.ArrowClosed, color: '#52525b', width: 14, height: 14 }
const ARROW_BRANCH = { type: MarkerType.ArrowClosed, color: '#3f3f46', width: 12, height: 12 }
const ARROW_GREEN = { type: MarkerType.ArrowClosed, color: '#059669', width: 16, height: 16 }

// --- Node components ---

function QuestionNode({ data }: { data: { question: string; answer: string; conclusion: string; step: number; sources: string[] } }) {
  const [open, setOpen] = useState(false)
  return (
    <div
      className="bg-zinc-800 border border-zinc-600 rounded-lg px-3 py-2 w-[280px] cursor-pointer hover:border-zinc-500 transition-colors"
      onClick={() => setOpen(!open)}
    >
      <Handle type="target" position={Position.Top} className="!bg-zinc-500 !w-2 !h-2" />
      <div className="flex items-start gap-2">
        <span className="shrink-0 text-[10px] font-mono text-cyan-500 bg-cyan-950/50 px-1.5 py-0.5 rounded">Q{data.step}</span>
        <div className="min-w-0">
          <div className="text-[11px] font-medium text-cyan-400 leading-snug">{data.question}</div>
          {!open && <div className="text-[10px] text-zinc-500 mt-0.5">click to expand</div>}
          {open && (
            <>
              <div className="text-[11px] text-zinc-300 leading-snug mt-1">{data.answer}</div>
              {data.conclusion && (
                <div className="text-[11px] text-zinc-400 italic mt-1">{data.conclusion}</div>
              )}
              {data.sources?.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-1.5">
                  {data.sources.map((s, i) => (
                    <span key={i} className="text-[9px] text-zinc-500 bg-zinc-900 px-1.5 py-0.5 rounded">{s}</span>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-zinc-500 !w-2 !h-2" />
      <Handle type="source" position={Position.Right} id="right" className="!bg-zinc-600 !w-1.5 !h-1.5" />
    </div>
  )
}

function JurisdictionNode({ data }: { data: { level: string; name: string; title: string; value: string | null; citation: string | null; sourceUrl: string | null; isGoverning: boolean } }) {
  const [open, setOpen] = useState(false)
  return (
    <div
      className={`rounded-lg px-3 py-2 w-[280px] cursor-pointer transition-colors ${
        data.isGoverning
          ? 'bg-zinc-800 border-2 border-cyan-600 shadow-lg shadow-cyan-900/20 hover:border-cyan-500'
          : 'bg-zinc-800/70 border border-zinc-700 hover:border-zinc-500'
      }`}
      onClick={() => setOpen(!open)}
    >
      <Handle type="target" position={Position.Left} className="!bg-zinc-600 !w-1.5 !h-1.5" />
      <Handle type="target" position={Position.Top} id="top" className="!bg-zinc-500 !w-2 !h-2" />
      <div className="flex items-center gap-2 mb-1">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-zinc-400">{data.level}</span>
        {data.name !== data.level && <span className="text-[10px] text-zinc-500">{data.name}</span>}
        {data.isGoverning && (
          <span className="text-[10px] font-semibold bg-emerald-900/60 text-emerald-300 px-1.5 py-0.5 rounded">GOVERNING</span>
        )}
      </div>
      <div className="text-[11px] font-medium text-zinc-200 leading-snug">{data.title}</div>
      {!open && <div className="text-[10px] text-zinc-500 mt-0.5">click for details</div>}
      {open && (
        <>
          {data.value && (
            <div className="text-[11px] text-zinc-300 leading-snug mt-1.5 bg-zinc-900/50 rounded px-2 py-1.5 border border-zinc-700/50">
              {data.value}
            </div>
          )}
          {data.citation && (
            <div className="text-[10px] text-zinc-500 mt-1.5">
              <span className="text-zinc-400 font-medium">Citation:</span> {data.citation}
            </div>
          )}
          {data.sourceUrl && (
            <a
              href={data.sourceUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-[10px] text-cyan-500 hover:text-cyan-400 mt-1"
              onClick={(e) => e.stopPropagation()}
            >
              <ExternalLink size={10} />
              View source
            </a>
          )}
        </>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-zinc-500 !w-2 !h-2" />
    </div>
  )
}

function ConclusionNode({ data }: { data: { text: string; precedenceType: string | null } }) {
  const ps = data.precedenceType ? PREC_COLORS[data.precedenceType] : null
  return (
    <div className="bg-zinc-800 border-2 border-emerald-600 rounded-lg px-3 py-2.5 w-[280px] shadow-lg shadow-emerald-900/30">
      <Handle type="target" position={Position.Top} className="!bg-emerald-500 !w-2.5 !h-2.5" />
      <div className="flex items-start gap-2">
        <span className="text-emerald-400 text-sm shrink-0">&#9733;</span>
        <span className="text-xs font-medium text-emerald-300 leading-snug">{data.text}</span>
      </div>
      {ps && (
        <span className={`inline-block mt-1.5 text-[10px] font-semibold px-1.5 py-0.5 rounded ${ps.bg} ${ps.text}`}>
          {data.precedenceType}
        </span>
      )}
    </div>
  )
}

const nodeTypes = { question: QuestionNode, jurisdiction: JurisdictionNode, conclusion: ConclusionNode }

// --- Layout ---

function layoutGraph(nodes: Node[], edges: Edge[]) {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'TB', nodesep: 40, ranksep: 60 })
  nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: n.measured?.height || NODE_H }))
  edges.forEach((e) => g.setEdge(e.source, e.target))
  dagre.layout(g)
  return {
    nodes: nodes.map((n) => {
      const p = g.node(n.id)
      return { ...n, position: { x: p.x - NODE_W / 2, y: p.y - (n.measured?.height || NODE_H) / 2 } }
    }),
    edges,
  }
}

// --- Build branching graph ---
// AI steps form main spine (vertical). Each step branches right to its jurisdiction level.
// Extra jurisdictions chain vertically below the last question.
// Conclusion connects from the governing jurisdiction or last node.

function buildGraph(
  steps: AIReasoningStep[] | undefined,
  category: ComplianceReasoningCategory,
): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = []
  const edges: Edge[] = []
  const hasSteps = steps && steps.length > 0
  let lastSpine: string | null = null

  function solidEdge(from: string, to: string, green = false) {
    edges.push({
      id: `e-${from}-${to}`,
      source: from,
      target: to,
      style: { stroke: green ? '#059669' : '#52525b', strokeWidth: green ? 2 : 1.5 },
      markerEnd: green ? ARROW_GREEN : ARROW,
    })
  }

  function branchEdge(from: string, to: string) {
    edges.push({
      id: `e-${from}-${to}`,
      source: from,
      sourceHandle: 'right',
      target: to,
      style: { stroke: '#3f3f46', strokeWidth: 1, strokeDasharray: '4 3' },
      markerEnd: ARROW_BRANCH,
    })
  }

  // AI reasoning steps — main vertical spine
  if (hasSteps) {
    steps.forEach((s, i) => {
      const id = `q-${i}`
      nodes.push({
        id,
        type: 'question',
        position: { x: 0, y: 0 },
        data: { question: s.question, answer: s.answer, conclusion: s.conclusion, step: i + 1, sources: s.sources || [] },
      })
      if (lastSpine) solidEdge(lastSpine, id)
      lastSpine = id
    })
  }

  // Jurisdiction nodes
  const levels = category.all_levels
  let lastJurisdiction: string | null = null

  levels.forEach((lv, i) => {
    const id = `j-${i}`
    nodes.push({
      id,
      type: 'jurisdiction',
      position: { x: 0, y: 0 },
      data: {
        level: lv.jurisdiction_level,
        name: lv.jurisdiction_name,
        title: lv.title,
        value: lv.current_value,
        citation: lv.statute_citation,
        sourceUrl: lv.source_url,
        isGoverning: lv.is_governing,
      },
    })

    if (hasSteps && i < steps.length) {
      // Branch from corresponding Q step
      branchEdge(`q-${i}`, id)
    } else if (hasSteps && i === steps.length) {
      // First extra jurisdiction chains from last Q step
      solidEdge(lastSpine!, id)
      lastSpine = id
    } else if (!hasSteps && i === 0) {
      // No steps — jurisdictions are the spine
      lastSpine = id
    } else {
      // Chain jurisdictions vertically (either extra ones or no-steps mode)
      if (lastJurisdiction) solidEdge(lastJurisdiction, id)
      else if (lastSpine) solidEdge(lastSpine, id)
      lastSpine = id
    }
    lastJurisdiction = id
  })

  // Conclusion — connects from the governing jurisdiction or last node
  const governing = levels.find((l) => l.is_governing)
  if (governing) {
    const govIdx = levels.indexOf(governing)
    const govId = `j-${govIdx}`
    const concId = 'conclusion'
    nodes.push({
      id: concId,
      type: 'conclusion',
      position: { x: 0, y: 0 },
      data: {
        text: `${governing.jurisdiction_name} ${governing.title} applies (${category.governing_level} level)`,
        precedenceType: category.precedence_type,
      },
    })
    // Connect from governing jurisdiction if it exists, otherwise last node
    solidEdge(govId, concId, true)
  }

  return layoutGraph(nodes, edges)
}

// --- Main ---

interface ComplianceDecisionTreeProps {
  category: ComplianceReasoningCategory
  aiSteps?: AIReasoningStep[]
}

export default function ComplianceDecisionTree({ category, aiSteps }: ComplianceDecisionTreeProps) {
  const { nodes, edges } = useMemo(() => buildGraph(aiSteps, category), [category, aiSteps])
  const height = Math.min(800, Math.max(350, nodes.length * 90))

  const onInit = useCallback((instance: { fitView: () => void }) => {
    setTimeout(() => instance.fitView(), 50)
  }, [])

  return (
    <div style={{ height }} className="w-full rounded-lg overflow-hidden border border-zinc-700/50 [&_.react-flow__node.selected]:!outline-none [&_.react-flow__node.selected]:!shadow-none">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onInit={onInit}
        fitView
        minZoom={0.3}
        maxZoom={1.5}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        panOnScroll
        zoomOnScroll={false}
        panOnDrag
      >
        <Background color="#27272a" gap={20} />
      </ReactFlow>
    </div>
  )
}
