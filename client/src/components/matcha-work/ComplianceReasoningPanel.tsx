import React, { useState, Suspense } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Shield, ChevronDown, MapPin, Loader2 } from 'lucide-react'
import type {
  AIReasoningStep,
  ComplianceReasoningLocation,
} from '../../types/matcha-work'

const ComplianceDecisionTree = React.lazy(() => import('./ComplianceDecisionTree'))

interface ComplianceReasoningPanelProps {
  locations: ComplianceReasoningLocation[]
  aiSteps?: AIReasoningStep[]
  referencedCategories?: string[]
  referencedLocations?: string[]
}

export default function ComplianceReasoningPanel({ locations, aiSteps, referencedCategories, referencedLocations }: ComplianceReasoningPanelProps) {
  const [expanded, setExpanded] = useState(false)
  const [selectedLocation, setSelectedLocation] = useState(0)
  const [selectedCategory, setSelectedCategory] = useState(0)

  // Filter to referenced locations, then referenced categories, removing empty locations
  // Gemini may return abbreviated labels (e.g. "San Francisco, CA") vs full labels
  // (e.g. "San Francisco (San Francisco, CA)"), so fall back to substring matching
  const filteredLocations = (() => {
    let filtered = referencedLocations?.length
      ? locations.filter((loc) =>
          referencedLocations.some((ref) => loc.location_label === ref || loc.location_label.includes(ref))
        )
      : locations

    if (referencedCategories?.length) {
      filtered = filtered
        .map((loc) => ({
          ...loc,
          categories: loc.categories.filter((cat) => referencedCategories.includes(cat.category)),
        }))
        .filter((loc) => loc.categories.length > 0)
    }

    return filtered.length > 0 ? filtered : locations
  })()

  const totalCategories = filteredLocations.reduce((sum, loc) => sum + loc.categories.length, 0)
  const currentLocation = filteredLocations[selectedLocation]
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
          — {totalCategories} categor{totalCategories === 1 ? 'y' : 'ies'} across {filteredLocations.length} location{filteredLocations.length === 1 ? '' : 's'}
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
              {filteredLocations.length > 1 && (
                <div className="flex flex-wrap gap-1.5">
                  {filteredLocations.map((loc, i) => (
                    <button
                      key={loc.location_id}
                      onClick={() => { setSelectedLocation(i); setSelectedCategory(0) }}
                      className={`flex items-center gap-1 text-xs px-2.5 py-1.5 rounded transition-colors ${
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
                      className="text-[11px] bg-violet-900/40 text-violet-300 border border-violet-700/40 px-1.5 py-0.5 rounded"
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
                        className={`text-xs px-2.5 py-1.5 rounded border transition-colors ${
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
                <div className="text-xs text-zinc-400 bg-zinc-800/50 rounded px-2 py-1.5 border border-zinc-700/30">
                  {currentCategory.reasoning_text}
                </div>
              )}

              {/* Data freshness indicator */}
              {currentCategory && (() => {
                const dates = currentCategory.all_levels
                  .map(l => l.last_verified_at)
                  .filter((d): d is string => !!d)
                  .map(d => new Date(d).getTime())
                const latest = dates.length ? new Date(Math.max(...dates)) : null
                if (!latest) return null
                return (
                  <div className="text-[10px] text-zinc-500 flex items-center gap-1">
                    <span>Data last verified:</span>
                    <span className="text-zinc-400">
                      {latest.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                    </span>
                  </div>
                )
              })()}

              {/* Decision tree — lazy loaded so it doesn't block the answer */}
              {currentCategory && (
                <Suspense
                  fallback={
                    <div className="flex items-center gap-2 py-4 justify-center text-xs text-zinc-500">
                      <Loader2 size={12} className="animate-spin" />
                      Building diagram...
                    </div>
                  }
                >
                  <ComplianceDecisionTree
                    category={currentCategory}
                    aiSteps={aiSteps}
                  />
                </Suspense>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
