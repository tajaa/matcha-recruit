import { useMemo, useCallback } from 'react'
import {
  ReactFlow,
  Background,
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

const NODE_WIDTH = 340
const NODE_HEIGHT_BASE = 60

const PRECEDENCE_COLORS: Record<string, { bg: string; text: string }> = {
  floor: { bg: 'bg-emerald-900/60', text: 'text-emerald-300' },
  ceiling: { bg: 'bg-amber-900/60', text: 'text-amber-300' },
  supersede: { bg: 'bg-red-900/60', text: 'text-red-300' },
  additive: { bg: 'bg-blue-900/60', text: 'text-blue-300' },
}

// --- Custom Node Components ---

function QuestionNode({ data }: { data: { question: string; answer: string; conclusion: string; sources: string[] } }) {
  return (
    <div className="bg-zinc-800 border border-zinc-600 rounded-lg px-3 py-2 min-w-[300px] max-w-[340px]">
      <Handle type="target" position={Position.Top} className="!bg-zinc-500" />
      <div className="text-xs font-medium text-cyan-400 mb-1">{data.question}</div>
      <div className="text-xs text-zinc-300">{data.answer}</div>
      {data.conclusion && (
        <div className="text-xs text-zinc-400 mt-1 italic">{data.conclusion}</div>
      )}
      {data.sources.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1">
          {data.sources.map((s, i) => (
            <span key={i} className="text-[10px] text-zinc-500 bg-zinc-900 px-1.5 py-0.5 rounded">
              {s}
            </span>
          ))}
        </div>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-zinc-500" />
    </div>
  )
}

function JurisdictionNode({ data }: { data: { level: string; name: string; title: string; value: string | null; citation: string | null; sourceUrl: string | null; isGoverning: boolean } }) {
  return (
    <div className={`rounded-lg px-3 py-2 min-w-[300px] max-w-[340px] ${
      data.isGoverning
        ? 'bg-zinc-800 border-2 border-cyan-600 shadow-lg shadow-cyan-900/20'
        : 'bg-zinc-800/70 border border-zinc-700'
    }`}>
      <Handle type="target" position={Position.Top} className="!bg-zinc-500" />
      <div className="flex items-center gap-2 mb-1">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-zinc-400">
          {data.level}
        </span>
        {data.name !== data.level && (
          <span className="text-[10px] text-zinc-500">({data.name})</span>
        )}
        {data.isGoverning && (
          <span className="text-[10px] font-semibold bg-emerald-900/60 text-emerald-300 px-1.5 py-0.5 rounded">
            GOVERNING
          </span>
        )}
      </div>
      <div className="text-xs font-medium text-zinc-200">{data.title}</div>
      {data.value && (
        <div className="text-xs text-zinc-400 mt-0.5">{data.value}</div>
      )}
      <div className="flex items-center gap-2 mt-1">
        {data.citation && (
          <span className="text-[10px] text-zinc-500">{data.citation}</span>
        )}
        {data.sourceUrl && (
          <a
            href={data.sourceUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-zinc-500 hover:text-cyan-400 transition-colors"
            onClick={(e) => e.stopPropagation()}
          >
            <ExternalLink size={10} />
          </a>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-zinc-500" />
    </div>
  )
}

function ConclusionNode({ data }: { data: { text: string; precedenceType: string | null } }) {
  const precStyle = data.precedenceType ? PRECEDENCE_COLORS[data.precedenceType] : null
  return (
    <div className="bg-zinc-800 border-2 border-emerald-600 rounded-lg px-3 py-2 min-w-[300px] max-w-[340px]">
      <Handle type="target" position={Position.Top} className="!bg-emerald-500" />
      <div className="flex items-center gap-2">
        <span className="text-emerald-400 text-sm">&#9733;</span>
        <span className="text-xs font-medium text-emerald-300">{data.text}</span>
      </div>
      {precStyle && (
        <span className={`inline-block mt-1 text-[10px] font-semibold px-1.5 py-0.5 rounded ${precStyle.bg} ${precStyle.text}`}>
          {data.precedenceType}
        </span>
      )}
    </div>
  )
}

const nodeTypes = {
  question: QuestionNode,
  jurisdiction: JurisdictionNode,
  conclusion: ConclusionNode,
}

// --- Layout helper ---

function getLayoutedElements(nodes: Node[], edges: Edge[]) {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'TB', nodesep: 30, ranksep: 50 })

  nodes.forEach((node) => {
    g.setNode(node.id, { width: NODE_WIDTH, height: node.measured?.height || NODE_HEIGHT_BASE })
  })
  edges.forEach((edge) => {
    g.setEdge(edge.source, edge.target)
  })

  dagre.layout(g)

  const layoutedNodes = nodes.map((node) => {
    const pos = g.node(node.id)
    return {
      ...node,
      position: {
        x: pos.x - NODE_WIDTH / 2,
        y: pos.y - (node.measured?.height || NODE_HEIGHT_BASE) / 2,
      },
    }
  })

  return { nodes: layoutedNodes, edges }
}

// --- Tree builders ---

function buildTreeFromAISteps(
  steps: AIReasoningStep[],
  category: ComplianceReasoningCategory,
): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = []
  const edges: Edge[] = []

  // Create question nodes from AI steps
  steps.forEach((step, i) => {
    const nodeId = `q-${i}`
    nodes.push({
      id: nodeId,
      type: 'question',
      position: { x: 0, y: 0 },
      data: {
        question: step.question,
        answer: step.answer,
        conclusion: step.conclusion,
        sources: step.sources || [],
      },
    })
    if (i > 0) {
      edges.push({
        id: `e-q${i - 1}-q${i}`,
        source: `q-${i - 1}`,
        target: nodeId,
        style: { stroke: '#52525b' },
      })
    }
  })

  // Add jurisdiction level nodes alongside
  category.all_levels.forEach((level, i) => {
    const nodeId = `j-${i}`
    nodes.push({
      id: nodeId,
      type: 'jurisdiction',
      position: { x: 0, y: 0 },
      data: {
        level: level.jurisdiction_level,
        name: level.jurisdiction_name,
        title: level.title,
        value: level.current_value,
        citation: level.statute_citation,
        sourceUrl: level.source_url,
        isGoverning: level.is_governing,
      },
    })
    // Connect question to corresponding jurisdiction if indices align
    if (i < steps.length) {
      edges.push({
        id: `e-q${i}-j${i}`,
        source: `q-${i}`,
        target: nodeId,
        style: { stroke: '#52525b', strokeDasharray: '4 2' },
      })
    }
  })

  // Add conclusion node
  const governing = category.all_levels.find((l) => l.is_governing)
  if (governing) {
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
    const lastQ = steps.length > 0 ? `q-${steps.length - 1}` : null
    const lastJ = category.all_levels.length > 0 ? `j-${category.all_levels.length - 1}` : null
    const connectFrom = lastQ || lastJ
    if (connectFrom) {
      edges.push({
        id: `e-${connectFrom}-conc`,
        source: connectFrom,
        target: concId,
        style: { stroke: '#059669' },
      })
    }
  }

  return getLayoutedElements(nodes, edges)
}

function buildTreeFromJurisdictions(category: ComplianceReasoningCategory): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = []
  const edges: Edge[] = []

  category.all_levels.forEach((level, i) => {
    const nodeId = `j-${i}`
    nodes.push({
      id: nodeId,
      type: 'jurisdiction',
      position: { x: 0, y: 0 },
      data: {
        level: level.jurisdiction_level,
        name: level.jurisdiction_name,
        title: level.title,
        value: level.current_value,
        citation: level.statute_citation,
        sourceUrl: level.source_url,
        isGoverning: level.is_governing,
      },
    })
    if (i > 0) {
      edges.push({
        id: `e-j${i - 1}-j${i}`,
        source: `j-${i - 1}`,
        target: nodeId,
        style: { stroke: '#52525b' },
      })
    }
  })

  // Add conclusion
  const governing = category.all_levels.find((l) => l.is_governing)
  if (governing) {
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
    if (category.all_levels.length > 0) {
      edges.push({
        id: `e-j${category.all_levels.length - 1}-conc`,
        source: `j-${category.all_levels.length - 1}`,
        target: concId,
        style: { stroke: '#059669' },
      })
    }
  }

  return getLayoutedElements(nodes, edges)
}

// --- Main Component ---

interface ComplianceDecisionTreeProps {
  category: ComplianceReasoningCategory
  aiSteps?: AIReasoningStep[]
}

export default function ComplianceDecisionTree({ category, aiSteps }: ComplianceDecisionTreeProps) {
  const { nodes, edges } = useMemo(() => {
    if (aiSteps && aiSteps.length > 0) {
      return buildTreeFromAISteps(aiSteps, category)
    }
    return buildTreeFromJurisdictions(category)
  }, [category, aiSteps])

  const nodeCount = nodes.length
  const height = Math.min(600, Math.max(200, nodeCount * 90))

  const onInit = useCallback((instance: { fitView: () => void }) => {
    setTimeout(() => instance.fitView(), 50)
  }, [])

  return (
    <div style={{ height }} className="w-full rounded-lg overflow-hidden border border-zinc-700/50">
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
        elementsSelectable={false}
        panOnDrag
        zoomOnScroll
      >
        <Background color="#27272a" gap={20} />
      </ReactFlow>
    </div>
  )
}
