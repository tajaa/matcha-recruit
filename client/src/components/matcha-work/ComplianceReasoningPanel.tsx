import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Shield, ChevronDown, MapPin } from 'lucide-react'
import type {
  AIReasoningStep,
  ComplianceReasoningLocation,
} from '../../types/matcha-work'
import ComplianceDecisionTree from './ComplianceDecisionTree'

interface ComplianceReasoningPanelProps {
  locations: ComplianceReasoningLocation[]
  aiSteps?: AIReasoningStep[]
}

export default function ComplianceReasoningPanel({ locations, aiSteps }: ComplianceReasoningPanelProps) {
  const [expanded, setExpanded] = useState(false)
  const [selectedLocation, setSelectedLocation] = useState(0)
  const [selectedCategory, setSelectedCategory] = useState(0)

  const totalCategories = locations.reduce((sum, loc) => sum + loc.categories.length, 0)
  const currentLocation = locations[selectedLocation]
  const currentCategory = currentLocation?.categories[selectedCategory]

  return (
    <div className="mt-2 rounded-lg border border-zinc-700/50 bg-zinc-900/50 overflow-hidden">
      {/* Collapsed summary bar */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-xs text-zinc-400 hover:text-zinc-300 hover:bg-zinc-800/50 transition-colors"
      >
        <Shield size={12} className="text-cyan-500 shrink-0" />
        <span className="font-medium">Compliance Evidence</span>
        <span className="text-zinc-500">
          — {totalCategories} categor{totalCategories === 1 ? 'y' : 'ies'} across {locations.length} location{locations.length === 1 ? '' : 's'}
        </span>
        <ChevronDown
          size={12}
          className={`ml-auto shrink-0 transition-transform ${expanded ? 'rotate-180' : ''}`}
        />
      </button>

      {/* Expanded content */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-3 pb-3 space-y-3">
              {/* Location selector */}
              {locations.length > 1 && (
                <div className="flex flex-wrap gap-1.5">
                  {locations.map((loc, i) => (
                    <button
                      key={loc.location_id}
                      onClick={() => { setSelectedLocation(i); setSelectedCategory(0) }}
                      className={`flex items-center gap-1 text-[11px] px-2 py-1 rounded transition-colors ${
                        i === selectedLocation
                          ? 'bg-cyan-900/40 text-cyan-300 border border-cyan-700/50'
                          : 'bg-zinc-800 text-zinc-400 border border-zinc-700/50 hover:text-zinc-300'
                      }`}
                    >
                      <MapPin size={10} />
                      {loc.location_label}
                    </button>
                  ))}
                </div>
              )}

              {/* Activated profiles */}
              {currentLocation?.activated_profiles.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {currentLocation.activated_profiles.map((p) => (
                    <span
                      key={p.label}
                      className="text-[10px] bg-violet-900/40 text-violet-300 border border-violet-700/40 px-1.5 py-0.5 rounded"
                    >
                      {p.label} — {p.categories.length} triggered
                    </span>
                  ))}
                </div>
              )}

              {/* Category selector */}
              {currentLocation && currentLocation.categories.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {currentLocation.categories.map((cat, i) => {
                    const precStyle = cat.precedence_type
                      ? {
                          floor: 'border-emerald-700/50 text-emerald-400',
                          ceiling: 'border-amber-700/50 text-amber-400',
                          supersede: 'border-red-700/50 text-red-400',
                          additive: 'border-blue-700/50 text-blue-400',
                        }[cat.precedence_type] || ''
                      : ''
                    return (
                      <button
                        key={cat.category}
                        onClick={() => setSelectedCategory(i)}
                        className={`text-[11px] px-2 py-1 rounded border transition-colors ${
                          i === selectedCategory
                            ? `bg-zinc-800 ${precStyle || 'border-zinc-600 text-zinc-200'}`
                            : 'bg-zinc-800/50 border-zinc-700/50 text-zinc-500 hover:text-zinc-400'
                        }`}
                      >
                        {cat.category.replace(/_/g, ' ')}
                        {cat.precedence_type && (
                          <span className="ml-1 opacity-60">({cat.precedence_type})</span>
                        )}
                      </button>
                    )
                  })}
                </div>
              )}

              {/* Reasoning text */}
              {currentCategory?.reasoning_text && (
                <div className="text-[11px] text-zinc-400 bg-zinc-800/50 rounded px-2 py-1.5 border border-zinc-700/30">
                  {currentCategory.reasoning_text}
                </div>
              )}

              {/* Decision tree */}
              {currentCategory && (
                <ComplianceDecisionTree
                  category={currentCategory}
                  aiSteps={aiSteps}
                />
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
